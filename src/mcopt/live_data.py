"""Read-only MCP Streamable HTTP client and atomic local fallback.

Never expose server errors, headers or credentials to the UI. Only the official
HTTPS host is permitted; redirects are disabled to protect Authorization.
"""
import json
import math
import os
import ssl
import certifi
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPSHandler

from .mcp_adapter import items_from_mcp, load_json, parse_nutrition_foods, match_nutrition

ALLOWED_TOOLS = frozenset({'query-meals', 'list-nutrition-foods'})


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('redirect disabled')


def credentials():
    token = os.environ.get('MCD_MCP_TOKEN', '').strip()
    if token:
        return token if token.startswith('Bearer ') else 'Bearer ' + token
    for directory in ('.cursor', '.workbuddy'):
        path = Path.home() / directory / 'mcp.json'
        if path.exists():
            cfg = json.loads(path.read_text()).get('mcpServers', {}).get('mcd-mcp', {})
            if cfg.get('url', '').rstrip('/') == 'https://mcp.mcd.cn':
                auth = cfg.get('headers', {}).get('Authorization')
                if auth:
                    return auth
    raise ValueError('credential unavailable')


class MCPClient:
    def __init__(self, authorization):
        self.authorization = authorization
        self.session = None
        self.protocol = '2024-11-05'
        self.counter = 0
        self.opener = build_opener(NoRedirect(), HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())))

    def request(self, method, params=None, notification=False):
        self.counter += 1
        body = dict(jsonrpc='2.0', method=method, params=params or {})
        if not notification:
            body['id'] = self.counter
        headers = {'Authorization': self.authorization, 'Content-Type': 'application/json',
                   'Accept': 'application/json, text/event-stream'}
        if self.session:
            headers['Mcp-Session-Id'] = self.session
            headers['MCP-Protocol-Version'] = self.protocol
        req = Request('https://mcp.mcd.cn', data=json.dumps(body).encode(), headers=headers)
        with self.opener.open(req, timeout=15) as response:
            self.session = response.headers.get('Mcp-Session-Id', self.session)
            if notification:
                return None
            if 'text/event-stream' in response.headers.get('Content-Type', ''):
                data, size = [], 0
                for raw in response:
                    size += len(raw)
                    if size > 8_000_000:
                        raise ValueError('response too large')
                    line = raw.decode().rstrip('\r\n')
                    if line.startswith('data:'):
                        data.append(line[5:].lstrip())
                    elif not line and data:
                        message = json.loads('\n'.join(data))
                        data = []
                        if message.get('id') == body['id']:
                            break
                else:
                    raise ValueError('missing response')
            else:
                raw = response.read(8_000_001)
                if len(raw) > 8_000_000:
                    raise ValueError('response too large')
                message = json.loads(raw)
        if message.get('error') or message.get('id') != body['id']:
            raise ValueError('MCP request failed')
        return message['result']

    def initialize(self):
        result = self.request('initialize', {
            'protocolVersion': self.protocol, 'capabilities': {},
            'clientInfo': {'name': 'mcopt-x-readonly', 'version': '1.0'}})
        self.protocol = result['protocolVersion']
        self.request('notifications/initialized', notification=True)

    def call(self, name, arguments):
        if name not in ALLOWED_TOOLS:
            raise ValueError('tool not allowed')
        result = self.request('tools/call', {'name': name, 'arguments': arguments})
        if result.get('isError'):
            raise ValueError('tool failed')
        if result.get('structuredContent') is not None:
            return result['structuredContent']
        texts = [c['text'] for c in result.get('content', []) if c.get('type') == 'text']
        return json.loads('\n'.join(texts))


@dataclass(frozen=True)
class MenuData:
    items: tuple
    missing: tuple
    source: str
    timestamp: str
    notice: str = ''


def convert(meals, nutrition, source, notice=''):
    if any(isinstance(p, dict) and p.get('success') is False for p in (meals, nutrition)):
        raise ValueError('business error')
    items = items_from_mcp(meals, nutrition)
    rows = parse_nutrition_foods(nutrition)
    known, missing = [], []
    for item in items:
        match = match_nutrition(item.name, rows)
        valid = match is not None and item.calories > 0 and item.effective_price > 0
        valid = valid and all(math.isfinite(x) and x >= 0 for x in
                              (item.price, item.calories, item.protein, item.discount))
        (known if valid else missing).append(item if valid else item.name)
    if not known:
        raise ValueError('no usable items')
    return MenuData(tuple(known), tuple(missing), source,
                    datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S'), notice)


def snapshot(fixtures, notice=''):
    return convert(load_json(str(fixtures / 'mcp_meals_min.json')),
                   load_json(str(fixtures / 'mcp_nutrition_min.json')),
                   '本地快照（模拟演示，非实时价格）', notice)


def refresh(fixtures, store_code, client_factory=None):
    try:
        if not store_code.strip():
            raise ValueError('store required')
        client = client_factory() if client_factory else MCPClient(credentials())
        client.initialize()
        meals = client.call('query-meals', {'storeCode': store_code.strip(), 'orderType': 1})
        nutrition = client.call('list-nutrition-foods', {})
        return convert(meals, nutrition, '实时 MCP · 到店自取 · 门店 ' + store_code.strip())
    except Exception:
        # Server exceptions may contain credentials; never render or persist them.
        return snapshot(fixtures, '实时刷新未成功，已回退本地快照。请检查门店编码、网络和本机 MCP 配置。')
