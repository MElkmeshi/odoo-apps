import requests


class SourceError(Exception):
    pass


class SourceClient:

    def __init__(self, url, database, login, api_key, timeout=300):
        self.url = url.rstrip('/')
        self.database = database
        self.login = login
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()
        self.uid = None

    def _rpc(self, service, method, *args):
        payload = {'jsonrpc': '2.0', 'method': 'call', 'params': {'service': service, 'method': method, 'args': args}}
        try:
            response = self.session.post(f'{self.url}/jsonrpc', json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as error:
            raise SourceError(f"Cannot reach the source database: {error}") from error
        if 'error' in data:
            error = data['error']
            detail = (error.get('data') or {}).get('message') or error.get('message')
            raise SourceError(f"{service}.{method} failed: {str(detail)[:1000]}")
        return data['result']

    def call(self, model, method, ids=None, **kwargs):
        if self.uid is None:
            self.uid = self._rpc('common', 'authenticate', self.database, self.login, self.api_key, {})
            if not self.uid:
                raise SourceError("The source database refused the login and API key.")
        args = [list(ids)] if ids is not None else []
        return self._rpc('object', 'execute_kw', self.database, self.uid, self.api_key, model, method, args, kwargs)
