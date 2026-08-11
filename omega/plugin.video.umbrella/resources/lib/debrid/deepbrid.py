# -*- coding: utf-8 -*-
"""
    Deepbrid debrid module for Umbrella.

    Deepbrid API:
    https://www.deepbrid.com/api-docs
"""

import time
import requests

from resources.lib.modules import control
from resources.lib.modules import log_utils


BASE_URL = 'https://www.deepbrid.com/api/v1/'
USER_AGENT = 'Umbrella-Deepbrid/1.3'

VIDEO_EXTENSIONS = (
    '.mkv', '.mp4', '.avi', '.mov', '.m4v',
    '.ts', '.wmv', '.mpg', '.mpeg', '.webm'
)


class Deepbrid:
    name = 'Deepbrid'

    def __init__(self):
        self.api_key = control.setting('deepbrid.token').strip()
        self.timeout = 30.0

        try:
            self.sort_priority = int(control.setting('deepbrid.priority') or '10')
        except:
            self.sort_priority = 10

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': USER_AGENT,
            'Accept': 'application/json'
        })

        self._set_auth(self.api_key)

    # -------------------------------------------------
    # Internal helpers
    # -------------------------------------------------

    def _set_auth(self, key):
        self.api_key = (key or '').strip()

        self.session.headers.pop('Authorization', None)
        self.session.headers.pop('X-Api-Key', None)

        if self.api_key:
            self.session.headers['Authorization'] = 'Bearer %s' % self.api_key
            self.session.headers['X-Api-Key'] = self.api_key

    def _request(self, method, endpoint, params=None, data=None,
                 json_data=None, files=None, silent=False, timeout=None):

        url = BASE_URL + endpoint.lstrip('/')
        request_timeout = self.timeout if timeout is None else timeout

        try:
            if method.upper() == 'GET':
                response = self.session.get(
                    url,
                    params=params,
                    timeout=request_timeout
                )
            else:
                response = self.session.post(
                    url,
                    params=params,
                    data=data,
                    json=json_data,
                    files=files,
                    timeout=request_timeout
                )

            if response.status_code == 401:
                if not silent:
                    control.notification(
                        title=self.name,
                        message='Invalid or expired API key',
                        icon='ERROR'
                    )
                return {}

            response.raise_for_status()

            result = response.json()

            if isinstance(result, dict):
                error = result.get('error')

                if error not in (None, 0, '0', False):
                    if not silent:
                        log_utils.log(
                            'Deepbrid API error: %s' % result,
                            level=log_utils.LOGWARNING
                        )
                    return {}

            return result

        except Exception as e:
            if not silent:
                log_utils.log(
                    'Deepbrid request error: %s' % str(e),
                    level=log_utils.LOGERROR
                )
            return {}

    def _get(self, endpoint, params=None, silent=False, timeout=None):
        return self._request(
            'GET',
            endpoint,
            params=params,
            silent=silent,
            timeout=timeout
        )

    def _post(self, endpoint, data=None, json_data=None,
              files=None, silent=False):
        return self._request(
            'POST',
            endpoint,
            data=data,
            json_data=json_data,
            files=files,
            silent=silent
        )

    # -------------------------------------------------
    # Authentication / Account
    # -------------------------------------------------

    def auth(self):
        control.sleep(200)

        key = control.dialog.input(
            'Deepbrid API Key',
            type=control.alpha_input
        )

        if not key:
            return

        key = key.strip()

        self._set_auth(key)

        info = self.account_info()

        if info and (
            info.get('username') or
            info.get('email') or
            info.get('type')
        ):
            control.setSetting('deepbrid.token', key)

            control.notification(
                title=self.name,
                message='Deepbrid authorized'
            )

            control.sleep(800)
            control.openSettings(
                '0.0',
                'plugin.video.umbrella'
            )
        else:
            control.notification(
                title=self.name,
                message='Invalid API key',
                icon='ERROR'
            )
            self.remove_auth()

    def remove_auth(self):
        self._set_auth('')

        control.setSetting(
            'deepbrid.token',
            ''
        )

        control.notification(
            title=self.name,
            message='Deepbrid authorization removed'
        )

    def account_info(self):
        if not self.api_key:
            return {}

        return self._get('user')

    def account_info_to_dialog(self):
        info = self.account_info()

        if not info:
            return control.notification(
                title=self.name,
                message='Could not get account info',
                icon='ERROR'
            )

        lines = []

        for key in (
            'username',
            'email',
            'type',
            'subscription',
            'expiration',
            'expires'
        ):
            if info.get(key):
                lines.append(
                    '%s: %s' %
                    (key.capitalize(), info[key])
                )

        control.dialog.ok(
            self.name,
            '\n'.join(lines) if lines else str(info)
        )

    # -------------------------------------------------
    # Hoster support
    # -------------------------------------------------

    def unrestrict_link(self, link, returnAll=False):
        if not self.api_key or not link:
            return None

        result = self._post(
            'generate/link',
            data={'link': link}
        )

        if not result:
            return None

        direct = (
            result.get('link') or
            result.get('download') or
            result.get('download_url')
        )

        if not direct:
            return None

        return result if returnAll else direct

    def get_hosts(self):
        hosts_dict = {
            'Deepbrid': []
        }

        try:
            # /hosts is public and returns:
            # [
            #   {"rapidgator.net": "up"},
            #   {"turbobit.net": "up"}
            # ]

            result = self._get(
                'hosts',
                silent=True
            )

            hosts = []

            if isinstance(result, list):
                for item in result:
                    if isinstance(item, dict):
                        for domain, status in item.items():
                            if domain:
                                # Do not advertise hosts that are
                                # explicitly down.
                                if status and str(status).lower().startswith('down'):
                                    continue

                                hosts.append(
                                    str(domain).lower()
                                )

            elif isinstance(result, dict):
                # Be tolerant of a wrapped API response.
                data = (
                    result.get('hosts') or
                    result.get('data') or
                    []
                )

                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            for domain in item:
                                hosts.append(
                                    str(domain).lower()
                                )

            hosts_dict['Deepbrid'] = list(
                set(hosts)
            )

        except:
            log_utils.error()

        return hosts_dict

    def valid_url(self, host):
        try:
            host = (host or '').lower().strip()

            if not host:
                return False

            hosts = self.get_hosts()

            if isinstance(hosts, dict):
                host_list = hosts.get(
                    self.name,
                    []
                )
            else:
                host_list = hosts or []

            for supported in host_list:
                supported = supported.lower()

                if (
                    host == supported or
                    host.endswith('.' + supported)
                ):
                    return True

            return False

        except:
            return False

    # -------------------------------------------------
    # Cache
    # -------------------------------------------------

    def check_cache(self, hashlist):
        """
        Deepbrid does not document a bulk hash-cache endpoint.

        Umbrella therefore treats torrents as unchecked and lets
        Deepbrid perform the transfer when the source is resolved.
        """
        return {}

    def check_cache_single(self, hash_string):
        return {}

    # -------------------------------------------------
    # Torrents
    # -------------------------------------------------

    def add_magnet(self, magnet):
        if not self.api_key or not magnet:
            return None

        # Deepbrid expects application/x-www-form-urlencoded.
        result = self._post(
            'torrents/add',
            data={'magnet': magnet}
        )

        log_utils.log(
            'Deepbrid add torrent response: %s' % repr(result),
            level=log_utils.LOGDEBUG
        )

        if not result:
            return None

        torrent_id = result.get('id')

        if not torrent_id:
            log_utils.log(
                'Deepbrid add torrent rejected: error=%s message=%s response=%s' % (
                    result.get('error'),
                    result.get('message'),
                    repr(result)
                ),
                level=log_utils.LOGWARNING
            )

        return torrent_id

    def create_transfer(self, magnet_url):
        result = self.add_magnet(magnet_url)

        if not result:
            return None

        torrent_id = (
            result.get('id') or
            result.get('torrent_id')
        )

        if not torrent_id:
            data = result.get('data')

            if isinstance(data, dict):
                torrent_id = data.get('id')

        return torrent_id

    def torrent_info(self, request_id='', timeout=None):
        if request_id:
            return self._get(
                'torrents/info',
                params={'id': request_id},
                timeout=timeout
            )

        return self._get('torrents/info', timeout=timeout)

    def list_transfer(self, transferid):
        return self.torrent_info(transferid)

    def _is_video_link(self, link, filename=''):
        text = '%s %s' % (
            link or '',
            filename or ''
        )

        text = text.lower()

        return any(
            ext in text
            for ext in VIDEO_EXTENSIONS
        )

    def _select_torrent_link(
        self,
        links,
        filename='',
        season=None,
        episode=None,
        title=None
    ):
        if not links:
            return None

        links = [
            i for i in links
            if isinstance(i, str) and i.startswith('http')
        ]

        if not links:
            return None

        # Deepbrid currently returns one URL per file.
        # Prefer a URL that looks like a playable video.
        video_links = [
            i for i in links
            if self._is_video_link(i, filename)
        ]

        if len(video_links) == 1:
            return video_links[0]

        if video_links:
            links = video_links

        # If there is only one file, there is nothing more to select.
        if len(links) == 1:
            return links[0]

        # Deepbrid's API currently does not expose the individual
        # filenames alongside each URL, so we cannot reliably map
        # multiple pack files to SxxExx here.
        #
        # Returning the first playable URL is preferable to trying
        # to manufacture a filename/file-index relationship that
        # the API does not provide.
        return None

    def resolve_magnet(
        self,
        magnet_url,
        info_hash=None,
        season=None,
        episode=None,
        title=None
    ):
        if not self.api_key or not magnet_url:
            return None

        try:
            deadline = time.monotonic() + 120.0

            torrent_id = self.create_transfer(
                magnet_url
            )

            if not torrent_id:
                log_utils.log(
                    'Deepbrid: torrent was not accepted',
                    level=log_utils.LOGWARNING
                )
                return None

            # Deepbrid does not give us a webhook/callback. Poll the
            # documented /torrents/info endpoint, but enforce the timeout
            # using wall-clock time so slow HTTP requests cannot stretch a
            # nominal two-minute poll into a much longer background worker.
            while time.monotonic() < deadline:

                if control.monitor.abortRequested():
                    return None

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break

                info = self.torrent_info(
                    torrent_id,
                    timeout=max(1.0, min(self.timeout, remaining))
                )

                if not info:
                    remaining = deadline - time.monotonic()
                    if remaining > 0:
                        time.sleep(min(2.0, remaining))
                    continue

                try:
                    error = int(
                        info.get('error', 0)
                    )
                except:
                    error = 0

                if error:
                    log_utils.log(
                        'Deepbrid torrent error: %s' % info,
                        level=log_utils.LOGWARNING
                    )
                    return None

                try:
                    progress = int(
                        info.get('progress', 0)
                    )
                except:
                    progress = 0

                links = info.get('links') or []

                # Deepbrid explicitly states that links are empty
                # until progress reaches 100.
                if progress >= 100 and links:

                    filename = (
                        info.get('filename') or
                        title or
                        ''
                    )

                    link = self._select_torrent_link(
                        links,
                        filename=filename,
                        season=season,
                        episode=episode,
                        title=title
                    )

                    if link:
                        return link

                    # A completed torrent with multiple links cannot be mapped
                    # to a filename with Deepbrid's current response shape.
                    # Polling again cannot make that selection deterministic.
                    return None

                # Don't hammer the API.
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    time.sleep(min(2.0, remaining))

            log_utils.log(
                'Deepbrid: torrent timed out after polling',
                level=log_utils.LOGWARNING
            )

            return None

        except Exception as e:
            log_utils.log(
                'Deepbrid resolve_magnet: %s' % str(e),
                level=log_utils.LOGERROR
            )
            return None

    def display_magnet_pack(
        self,
        magnet_url,
        info_hash=None
    ):
        """
        Deepbrid's current torrent-info API does not expose
        per-file names alongside the returned links.

        Returning an empty list prevents Umbrella's pack dialog
        from presenting misleading file choices.
        """
        return []

    def add_uncached_torrent(
        self,
        magnet_url,
        pack=False
    ):
        return bool(
            self.create_transfer(magnet_url)
        )

    # -------------------------------------------------
    # Usenet
    # -------------------------------------------------

    def add_usenet(
        self,
        nzb_url=None,
        nzb_file=None
    ):
        if not self.api_key:
            return None

        if nzb_url:
            return self._post(
                'usenet/add',
                data={'nzb_url': nzb_url}
            )

        if nzb_file:
            try:
                with open(nzb_file, 'rb') as f:
                    return self._post(
                        'usenet/add',
                        files={'nzb_file': f}
                    )
            except:
                log_utils.error()

        return None

    def usenet_uploads(self):
        result = self._get(
            'usenet/uploads'
        )

        if not result:
            return []

        return (
            result.get('items') or
            result.get('data') or
            []
        )

    def usenet_info(self, upload_id):
        return self._get(
            'usenet/uploads/info',
            params={'id': upload_id}
        )

    def user_cloud_usenet(self, request_id=None):
        if request_id:
            return self.usenet_info(
                request_id
            )

        return {
            'items': self.usenet_uploads()
        }

    def unrestrict_usenet(self, file_link_or_id):
        if not file_link_or_id:
            return None

        if str(file_link_or_id).startswith('http'):
            return file_link_or_id

        return None

    def resolve_usenet(
        self,
        nzb_url,
        title=None,
        season=None,
        episode=None
    ):
        added = self.add_usenet(
            nzb_url=nzb_url
        )

        if not added:
            return None

        upload_id = (
            added.get('id') or
            added.get('upload_id')
        )

        if not upload_id:
            data = added.get('data')

            if isinstance(data, dict):
                upload_id = data.get('id')

        if not upload_id:
            return None

        for _ in range(30):

            if control.monitor.abortRequested():
                return None

            info = self.usenet_info(
                upload_id
            )

            files = (
                info.get('files', [])
                if isinstance(info, dict)
                else []
            )

            candidates = []

            for item in files:
                if not isinstance(item, dict):
                    continue

                name = (
                    item.get('name') or
                    item.get('filename') or
                    ''
                )

                link = item.get('link')

                if (
                    link and
                    self._is_video_link(link, name)
                ):
                    candidates.append(
                        link
                    )

            if candidates:
                return candidates[0]

            time.sleep(2)

        return None

    # -------------------------------------------------
    # Cloud
    # -------------------------------------------------

    def user_cloud(self, request_id=None):
        if request_id:
            return self.torrent_info(
                request_id
            )

        return self.torrent_info()

    def user_cloud_to_listItem(self, folder_id=None):
        return []

    def browse_user_torrents(
        self,
        folder_id,
        mediatype
    ):
        return []

    # -------------------------------------------------
    # Delete operations
    # -------------------------------------------------

    def delete_torrent(self, request_id=''):
        return False

    def delete_usenet(self, request_id=''):
        return False

    def delete_torrent_queued(
        self,
        request_id=''
    ):
        return False

    def delete_webdl(
        self,
        request_id=''
    ):
        return False

    def delete_user_torrent(
        self,
        request_id,
        mediatype,
        name,
        multi=False
    ):
        return False

    def delete_all_user_torrents(self):
        control.notification(
            title=self.name,
            message='Delete not supported by Deepbrid API'
        )
        return False

    def user_cloud_clear(self):
        control.notification(
            title=self.name,
            message='Delete not supported by Deepbrid API'
        )
        return False

    def unrestrict_webdl(self, file_id):
        return None

    def queued_torrents(self):
        return []