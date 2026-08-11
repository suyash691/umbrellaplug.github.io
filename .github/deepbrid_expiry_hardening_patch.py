from pathlib import Path
import re

ROOT = Path('omega/plugin.video.umbrella')
DEEPBRID = ROOT / 'resources/lib/debrid/deepbrid.py'
SERVICE = ROOT / 'service.py'
SETTINGS = ROOT / 'resources/settings.xml'


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected 1 match, found {count}')
    return text.replace(old, new, 1)


def regex_once(text, pattern, replacement, label):
    new_text, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f'{label}: expected 1 regex match, found {count}')
    return new_text


# ------------------------------------------------------------------
# deepbrid.py
# ------------------------------------------------------------------
text = DEEPBRID.read_text(encoding='utf-8')

text = replace_once(
    text,
    "from resources.lib.modules.source_utils import (\n    seas_ep_filter,\n    extras_filter\n)",
    "from resources.lib.modules.source_utils import (\n    seas_ep_filter,\n    extras_filter,\n    supported_video_extensions\n)",
    'source_utils import'
)

text = regex_once(
    text,
    r"VIDEO_EXTENSIONS = \(\n.*?\n\)\n",
    "VIDEO_EXTENSIONS = tuple(supported_video_extensions())\n",
    'VIDEO_EXTENSIONS'
)

new_probe_links = '''    def _probe_torrent_links(self, links, indexes=None):
        if not links:
            return []

        if indexes is None:
            indexed_links = list(enumerate(links))
        else:
            indexed_links = [
                (int(index), link)
                for index, link in zip(indexes, links)
            ]

        if not indexed_links:
            return []

        results = []

        # Keep concurrency conservative. These requests follow the file-host
        # redirect and can be substantially slower than filename-only probes.
        workers = min(4, len(indexed_links))

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    self._probe_torrent_link,
                    link,
                    index
                ): index
                for index, link in indexed_links
            }

            for future in as_completed(futures):
                index = futures[future]
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception as e:
                    log_utils.log(
                        'Deepbrid probe worker failed: index=%s error=%s' % (
                            index,
                            type(e).__name__
                        ),
                        level=log_utils.LOGWARNING
                    )

        results.sort(key=lambda item: item.get('index', 0))
        return results

'''
text = regex_once(
    text,
    r"    def _probe_torrent_links\(self, links\):\n.*?(?=    def _probe_torrent_link\(self, link, index\):)",
    new_probe_links,
    '_probe_torrent_links'
)

new_probe_link = '''    def _probe_torrent_link(self, link, index):
        response = None

        try:
            response = requests.get(
                link,
                headers={
                    'Range': 'bytes=0-0',
                    'Accept-Encoding': 'identity'
                },
                allow_redirects=True,
                stream=True,
                timeout=(10, 60)
            )

            filename = self._filename_from_headers(response)
            content_type = (
                response.headers.get('Content-Type', '')
                .split(';', 1)[0]
                .strip()
                .lower()
            )

            size = 0
            content_range = response.headers.get('Content-Range', '')
            if '/' in content_range:
                try:
                    size = int(content_range.rsplit('/', 1)[1])
                except Exception:
                    pass

            if not size:
                try:
                    size = int(response.headers.get('Content-Length') or 0)
                except Exception:
                    pass

            # Do not retain or log Deepbrid/CDN one-time URLs. Callers only
            # need stable selection metadata from a probe.
            result = {
                'index': index,
                'filename': filename,
                'content_type': content_type,
                'size': size,
                'status': response.status_code
            }

            log_utils.log(
                'Deepbrid file probe: index=%s status=%s filename=%s size=%s' % (
                    index,
                    response.status_code,
                    filename,
                    size
                ),
                level=log_utils.LOGDEBUG
            )
            return result

        except Exception as e:
            log_utils.log(
                'Deepbrid file probe failed: index=%s error=%s' % (
                    index,
                    type(e).__name__
                ),
                level=log_utils.LOGWARNING
            )
            return None

        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass

'''
text = regex_once(
    text,
    r"    def _probe_torrent_link\(self, link, index\):\n.*?(?=    def _probe_torrent_link_name\(self, link, index\):)",
    new_probe_link,
    '_probe_torrent_link'
)

new_probe_name = '''    def _probe_torrent_link_name(self, link, index):
        response = None

        try:
            # Filename-only probe: never follow the one-time redirect to the
            # file host. The redirect path is enough to recover the filename.
            response = requests.get(
                link,
                headers={
                    'Range': 'bytes=0-0',
                    'Accept-Encoding': 'identity'
                },
                allow_redirects=False,
                stream=True,
                timeout=(5, 10)
            )

            location = response.headers.get('Location') or ''
            filename = None
            if location:
                try:
                    path = unquote(urlparse(location).path)
                    filename = os.path.basename(path)
                except Exception:
                    pass

            # Keep the redirect URL local only. It is one-time data and should
            # never enter probe dictionaries or debug logs.
            result = {
                'index': index,
                'filename': filename,
                'status': response.status_code
            }

            log_utils.log(
                'Deepbrid fast file probe: index=%s status=%s filename=%s' % (
                    index,
                    response.status_code,
                    filename
                ),
                level=log_utils.LOGDEBUG
            )
            return result

        except Exception as e:
            log_utils.log(
                'Deepbrid fast probe failed: index=%s error=%s' % (
                    index,
                    type(e).__name__
                ),
                level=log_utils.LOGWARNING
            )
            return None

        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass

'''
text = regex_once(
    text,
    r"    def _probe_torrent_link_name\(self, link, index\):\n.*?(?=    def _probe_torrent_link_names\(self, links\):)",
    new_probe_name,
    '_probe_torrent_link_name'
)

new_episode_movie = '''    def _find_episode_file(self, links, season, episode):
        if not links:
            return None

        # Probe small batches and stop as soon as the requested episode is
        # found. A failed/no-filename short-link probe gets one fast retry,
        # but only when the first pass did not already find the episode.
        batch_size = 8

        for start in range(0, len(links), batch_size):
            batch = list(
                enumerate(
                    links[start:start + batch_size],
                    start=start
                )
            )
            results = {}

            with ThreadPoolExecutor(
                max_workers=min(batch_size, len(batch))
            ) as executor:
                futures = {
                    executor.submit(
                        self._probe_torrent_link_name,
                        link,
                        index
                    ): index
                    for index, link in batch
                }

                for future in as_completed(futures):
                    index = futures[future]
                    try:
                        item = future.result()
                    except Exception:
                        item = None
                    if item:
                        results[index] = item

            matches = [
                item for item in results.values()
                if item.get('filename')
                and seas_ep_filter(
                    season,
                    episode,
                    item.get('filename')
                )
            ]

            if not matches:
                retry_items = [
                    (index, link)
                    for index, link in batch
                    if not (results.get(index) or {}).get('filename')
                ]

                if retry_items:
                    log_utils.log(
                        'Deepbrid retrying fast filename probes: indexes=%s' %
                        [item[0] for item in retry_items],
                        level=log_utils.LOGDEBUG
                    )
                    with ThreadPoolExecutor(
                        max_workers=min(4, len(retry_items))
                    ) as executor:
                        futures = {
                            executor.submit(
                                self._probe_torrent_link_name,
                                link,
                                index
                            ): index
                            for index, link in retry_items
                        }
                        for future in as_completed(futures):
                            index = futures[future]
                            try:
                                item = future.result()
                            except Exception:
                                item = None
                            if item:
                                results[index] = item

                    matches = [
                        item for item in results.values()
                        if item.get('filename')
                        and seas_ep_filter(
                            season,
                            episode,
                            item.get('filename')
                        )
                    ]

            if matches:
                matches.sort(key=lambda item: item.get('index', 0))
                selected = matches[0]
                log_utils.log(
                    'Deepbrid episode fast match: '
                    'S%sE%s index=%s filename=%s' % (
                        str(season).zfill(2),
                        str(episode).zfill(2),
                        selected.get('index'),
                        selected.get('filename')
                    ),
                    level=log_utils.LOGDEBUG
                )
                return selected

        log_utils.log(
            'Deepbrid: no file matched S%sE%s' % (
                str(season).zfill(2),
                str(episode).zfill(2)
            ),
            level=log_utils.LOGWARNING
        )
        return None

    def _find_movie_file(self, links, title=None):
        if not links:
            return None

        # First recover filenames without following Deepbrid's one-time short
        # URLs. This cheaply removes samples/extras/non-video files. Any entry
        # whose filename could not be recovered remains eligible for the old
        # full Range probe so this optimization cannot hide a valid movie.
        name_probes = self._probe_torrent_link_names(links)
        by_index = {
            item.get('index'): item
            for item in name_probes
            if isinstance(item, dict) and item.get('index') is not None
        }

        title_lower = (title or '').lower()
        extras = tuple(
            extra for extra in extras_filter()
            if extra not in title_lower
        )

        candidates = []
        unknown = []
        for index in range(len(links)):
            filename = (by_index.get(index) or {}).get('filename') or ''
            if not filename:
                unknown.append(index)
                continue

            lower_name = filename.lower()
            if not lower_name.endswith(VIDEO_EXTENSIONS):
                continue
            if any(extra in lower_name for extra in extras):
                continue
            candidates.append(index)

        if len(candidates) == 1 and not unknown:
            selected = dict(by_index[candidates[0]])
            selected.setdefault('content_type', '')
            selected.setdefault('size', 0)
            log_utils.log(
                'Deepbrid movie fast match: index=%s filename=%s' % (
                    selected.get('index'),
                    selected.get('filename')
                ),
                level=log_utils.LOGDEBUG
            )
            return selected

        probe_indexes = sorted(set(candidates + unknown))
        if not probe_indexes:
            # Preserve the known-working fallback for unusual files whose
            # extensions do not reveal that they are video.
            probe_indexes = list(range(len(links)))

        log_utils.log(
            'Deepbrid movie full-probe candidates: %s of %s' % (
                len(probe_indexes),
                len(links)
            ),
            level=log_utils.LOGDEBUG
        )

        probes = self._probe_torrent_links(
            [links[index] for index in probe_indexes],
            indexes=probe_indexes
        )
        return self._select_probed_file(probes, title=title)

'''
text = regex_once(
    text,
    r"    def _find_episode_file\(self, links, season, episode\):\n.*?(?=    def _is_video_probe\(self, item\):)",
    new_episode_movie,
    '_find_episode_file + _find_movie_file'
)

new_is_video = '''    def _is_video_probe(self, item):
        filename = (item.get('filename') or '').lower()
        content_type = (item.get('content_type') or '').lower()

        audio_extensions = (
            '.eac3', '.ac3', '.dts', '.aac', '.flac',
            '.mp3', '.m4a', '.wav', '.ogg', '.opus'
        )

        if filename.endswith(audio_extensions):
            return False
        if filename.endswith(VIDEO_EXTENSIONS):
            return True
        if content_type.startswith('video/'):
            return True
        if content_type.startswith('audio/'):
            return False
        return False

'''
text = regex_once(
    text,
    r"    def _is_video_probe\(self, item\):\n.*?(?=    def _filename_from_headers\(self, response\):)",
    new_is_video,
    '_is_video_probe'
)

old_movie_select = '''            else:
                # Keep the known-working movie path unchanged.
                probes = self._probe_torrent_links(
                    links
                )

                selected = self._select_probed_file(
                    probes,
                    title=title
                )
'''
new_movie_select = '''            else:
                selected = self._find_movie_file(
                    links,
                    title=title
                )
'''
text = replace_once(
    text,
    old_movie_select,
    new_movie_select,
    'movie selection path'
)

text = replace_once(
    text,
    "        log_utils.log(\n            'Deepbrid Usenet selected file: %s' % repr(selected),\n            level=log_utils.LOGDEBUG\n        )\n",
    "        log_utils.log(\n            'Deepbrid Usenet selected file: name=%s size=%s' % (\n                selected.get('name'),\n                selected.get('size')\n            ),\n            level=log_utils.LOGDEBUG\n        )\n",
    'Usenet selected log redaction'
)

DEEPBRID.write_text(text, encoding='utf-8')


# ------------------------------------------------------------------
# service.py - Deepbrid expiry notification
# ------------------------------------------------------------------
service = SERVICE.read_text(encoding='utf-8')
service = replace_once(
    service,
    "\t\tfrom resources.lib.debrid import premiumize\n\t\tfrom resources.lib.debrid import realdebrid\n",
    "\t\tfrom resources.lib.debrid import premiumize\n\t\tfrom resources.lib.debrid import realdebrid\n\t\tfrom resources.lib.debrid import deepbrid\n",
    'expiry imports'
)

expiry_block = '''
\t\tif control.setting('deepbrid.token') != '' and control.setting('deepbridexpirynotice') == 'true':
\t\t\ttry:
\t\t\t\taccount_info = deepbrid.Deepbrid().account_info()
\t\t\texcept Exception:
\t\t\t\taccount_info = None
\t\t\t\tlog_utils.error()
\t\t\tif account_info and not account_info.get('error'):
\t\t\t\texpiration = account_info.get('expiration')
\t\t\t\ttry:
\t\t\t\t\texpires = datetime.strptime(str(expiration), '%Y-%m-%d')
\t\t\t\texcept Exception:
\t\t\t\t\texpires = None
\t\t\t\t\tif not expiration:
\t\t\t\t\t\tcontrol.notification(
\t\t\t\t\t\t\tmessage='Deepbrid Account has no expiration. Invalid or free account.',
\t\t\t\t\t\t\ticon=control.joinPath(control.artPath(), 'deepbrid.png')
\t\t\t\t\t\t)
\t\t\t\tif expires:
\t\t\t\t\tdays_remaining = (expires.date() - datetime.today().date()).days
\t\t\t\t\tif days_remaining >= 0:
\t\t\t\t\t\tif self.withinRangeCheck('deepbrid', days_remaining):
\t\t\t\t\t\t\tcontrol.notification(
\t\t\t\t\t\t\t\tmessage='Deepbrid Account expires in %s days' % days_remaining,
\t\t\t\t\t\t\t\ticon=control.joinPath(control.artPath(), 'deepbrid.png')
\t\t\t\t\t\t\t)
'''
service = replace_once(
    service,
    "\n\tdef withinRangeCheck(self, debrid_provider, days_remaining):\n",
    expiry_block + "\n\tdef withinRangeCheck(self, debrid_provider, days_remaining):\n",
    'Deepbrid expiry block'
)
SERVICE.write_text(service, encoding='utf-8')


# ------------------------------------------------------------------
# settings.xml - expiry toggle + hidden notification-range state
# Preserve the existing UTF-8 BOM.
# ------------------------------------------------------------------
raw = SETTINGS.read_bytes()
had_bom = raw.startswith(b'\xef\xbb\xbf')
settings = raw.decode('utf-8-sig')

expiry_settings = '''\n\t\t\t\t<setting id="deepbridexpirynotice" type="boolean" label="40120" help="">
\t\t\t\t\t<level>0</level>
\t\t\t\t\t<default>true</default>
\t\t\t\t\t<dependencies>
\t\t\t\t\t\t<dependency type="visible">
\t\t\t\t\t\t\t<and>
\t\t\t\t\t\t\t\t<condition operator="!is" setting="deepbrid.token"/>
\t\t\t\t\t\t\t\t<condition operator="is" setting="deepbrid.enable">true</condition>
\t\t\t\t\t\t\t</and>
\t\t\t\t\t\t</dependency>
\t\t\t\t\t</dependencies>
\t\t\t\t\t<control type="toggle"/>
\t\t\t\t</setting>
\t\t\t\t<setting id="deepbrid.notification.range" type="string" label="" help="">
\t\t\t\t\t<level>0</level>
\t\t\t\t\t<default/>
\t\t\t\t\t<constraints>
\t\t\t\t\t\t<allowempty>true</allowempty>
\t\t\t\t\t</constraints>
\t\t\t\t\t<dependencies>
\t\t\t\t\t\t<dependency type="visible">
\t\t\t\t\t\t\t<condition on="property" name="InfoBool">false</condition>
\t\t\t\t\t\t</dependency>
\t\t\t\t\t</dependencies>
\t\t\t\t\t<control type="edit" format="string"></control>
\t\t\t\t</setting>
'''
marker = '\n\t\t\t\t<setting id="db_cloud.enabled" type="boolean" label="32050" help="">'
settings = replace_once(
    settings,
    marker,
    expiry_settings + marker,
    'Deepbrid expiry settings'
)
encoded = settings.encode('utf-8')
if had_bom:
    encoded = b'\xef\xbb\xbf' + encoded
SETTINGS.write_bytes(encoded)

print('Deepbrid expiry/performance/logging hardening patch applied')
