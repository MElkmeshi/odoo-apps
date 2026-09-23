import requests


class SourceError(Exception):
    pass


class SourceClient:

    def __init__(self, url, database, api_key, timeout=300):
        self.url = url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'bearer {api_key}',
            'X-Odoo-Database': database,
        })

    def call(self, model, method, ids=None, **kwargs):
        payload = dict(kwargs)
        if ids is not None:
            payload['ids'] = list(ids)
        try:
            response = self.session.post(
                f'{self.url}/json/2/{model}/{method}', json=payload, timeout=self.timeout,
            )
        except requests.RequestException as error:
            raise SourceError(f"Cannot reach the source database: {error}") from error
        if response.status_code != 200:
            try:
                detail = response.json().get('message') or response.text
            except ValueError:
                detail = response.text
            raise SourceError(f"{model}.{method} failed ({response.status_code}): {detail[:1000]}")
        return response.json()
