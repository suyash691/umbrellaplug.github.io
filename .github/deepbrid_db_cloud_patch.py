from pathlib import Path

root = Path('.')
deepbrid_path = root / 'omega/plugin.video.umbrella/resources/lib/debrid/deepbrid.py'
sources_path = root / 'omega/plugin.video.umbrella/resources/lib/modules/sources.py'
settings_path = root / 'omega/plugin.video.umbrella/resources/settings.xml'

# --- deepbrid.py -----------------------------------------------------------
deepbrid = deepbrid_path.read_text(encoding='utf-8')

if 'def torrent_list(self):' not in deepbrid:
    marker = "    def _probe_torrent_links(self, links):\n"
    insert = '''    def torrent_list(self):\n        return self._torrent_list()\n\n'''
    if marker not in deepbrid:
        raise SystemExit('torrent_list insertion marker not found')
    deepbrid = deepbrid.replace(marker, insert + marker, 1)

if 'def cached_torrent_file_metadata(' not in deepbrid:
    marker = "    def _find_episode_file(self, links, season, episode):\n"
    insert = '''    def torrent_file_metadata(\n        self,\n        request_id,\n        expected_count=0,\n        torrent_name=''\n    ):\n        \"\"\"Return stable torrent file metadata without caching short URLs.\"\"\"\n        info = self.torrent_info(request_id)\n        if not isinstance(info, dict):\n            return {}\n\n        error = info.get('error')\n        if error not in (None, 0, '0', False):\n            return {}\n\n        try:\n            progress = int(info.get('progress') or 0)\n        except Exception:\n            progress = 0\n\n        links = info.get('links') or []\n        if progress < 100 or not links:\n            return {}\n\n        try:\n            expected_count = int(expected_count or len(links))\n        except Exception:\n            expected_count = len(links)\n\n        if expected_count != len(links):\n            return {}\n\n        probes = self._probe_torrent_link_names(links)\n        by_index = {\n            item.get('index'): item\n            for item in probes\n            if isinstance(item, dict) and item.get('index') is not None\n        }\n\n        # Retry only the entries whose short redirect did not reveal a name.\n        # This keeps the initial metadata build robust without following the\n        # CDN/file-host redirect or re-probing the whole pack.\n        missing = [\n            index for index in range(len(links))\n            if not (by_index.get(index) or {}).get('filename')\n        ]\n        if missing:\n            with ThreadPoolExecutor(\n                max_workers=min(4, len(missing))\n            ) as executor:\n                futures = {\n                    executor.submit(\n                        self._probe_torrent_link_name,\n                        links[index],\n                        index\n                    ): index\n                    for index in missing\n                }\n                for future in as_completed(futures):\n                    try:\n                        item = future.result()\n                        if item:\n                            by_index[item.get('index')] = item\n                    except Exception:\n                        pass\n\n        files = []\n        for index in range(len(links)):\n            filename = (by_index.get(index) or {}).get('filename') or ''\n            if not filename and len(links) == 1:\n                filename = info.get('filename') or torrent_name or ''\n            files.append({\n                'index': index,\n                'filename': filename\n            })\n\n        named_count = len([item for item in files if item.get('filename')])\n        if not named_count:\n            return {}\n\n        log_utils.log(\n            'Deepbrid torrent metadata scan: id=%s files=%s named=%s' % (\n                request_id,\n                len(files),\n                named_count\n            ),\n            level=log_utils.LOGDEBUG\n        )\n\n        return {\n            'count': len(links),\n            'files': files\n        }\n\n    def cached_torrent_file_metadata(\n        self,\n        request_id,\n        expected_count=0,\n        torrent_name=''\n    ):\n        # File ordering/names are stable, while Deepbrid's short URLs are\n        # explicitly one-time. Cache only index/name metadata for 24 hours.\n        return cache.get(\n            self.torrent_file_metadata,\n            24,\n            str(request_id),\n            int(expected_count or 0),\n            str(torrent_name or '')\n        ) or {}\n\n'''
    if marker not in deepbrid:
        raise SystemExit('torrent metadata insertion marker not found')
    deepbrid = deepbrid.replace(marker, insert + marker, 1)

if 'def cached_usenet_file_metadata(' not in deepbrid:
    marker = "    def resolve_usenet(\n"
    insert = '''    def usenet_file_metadata(self, upload_id, upload_title=''):\n        \"\"\"Return stable NZB file metadata without caching direct links.\"\"\"\n        info = self.usenet_info(upload_id)\n        if not isinstance(info, dict):\n            return {}\n\n        error = info.get('error')\n        if error not in (None, 0, '0', False):\n            return {}\n\n        raw_files = info.get('files') or []\n        if not raw_files:\n            return {}\n\n        # Do not cache an upload that has not exposed any playable links yet.\n        if not any(\n            isinstance(item, dict) and item.get('link')\n            for item in raw_files\n        ):\n            return {}\n\n        files = []\n        for index, item in enumerate(raw_files):\n            if not isinstance(item, dict):\n                files.append({\n                    'index': index,\n                    'filename': '',\n                    'size': 0\n                })\n                continue\n\n            try:\n                size = int(item.get('size') or 0)\n            except Exception:\n                size = 0\n\n            files.append({\n                'index': index,\n                'filename': item.get('name') or item.get('filename') or '',\n                'size': size\n            })\n\n        return {\n            'count': len(raw_files),\n            'files': files\n        }\n\n    def cached_usenet_file_metadata(self, upload_id, upload_title=''):\n        return cache.get(\n            self.usenet_file_metadata,\n            24,\n            str(upload_id),\n            str(upload_title or '')\n        ) or {}\n\n'''
    if marker not in deepbrid:
        raise SystemExit('Usenet metadata insertion marker not found')
    deepbrid = deepbrid.replace(marker, insert + marker, 1)

if 'def resolve_cloud_torrent_file(' not in deepbrid:
    marker = "    def user_cloud(self, request_id=None):\n"
    insert = '''    def resolve_cloud_torrent_file(\n        self,\n        request_id,\n        index,\n        expected_count\n    ):\n        \"\"\"Resolve cached torrent index against fresh one-time links.\"\"\"\n        info = self.torrent_info(request_id)\n        if not isinstance(info, dict):\n            return None\n\n        error = info.get('error')\n        if error not in (None, 0, '0', False):\n            return None\n\n        links = info.get('links') or []\n        try:\n            index = int(index)\n            expected_count = int(expected_count)\n        except Exception:\n            return None\n\n        if len(links) != expected_count or index < 0 or index >= len(links):\n            log_utils.log(\n                'Deepbrid cloud torrent mapping changed: '\n                'id=%s expected=%s actual=%s index=%s' % (\n                    request_id,\n                    expected_count,\n                    len(links),\n                    index\n                ),\n                level=log_utils.LOGWARNING\n            )\n            return None\n\n        return links[index]\n\n    def resolve_cloud_usenet_file(\n        self,\n        upload_id,\n        index,\n        expected_count\n    ):\n        \"\"\"Resolve cached NZB index against a fresh upload-info response.\"\"\"\n        info = self.usenet_info(upload_id)\n        if not isinstance(info, dict):\n            return None\n\n        error = info.get('error')\n        if error not in (None, 0, '0', False):\n            return None\n\n        files = info.get('files') or []\n        try:\n            index = int(index)\n            expected_count = int(expected_count)\n        except Exception:\n            return None\n\n        if len(files) != expected_count or index < 0 or index >= len(files):\n            return None\n\n        item = files[index]\n        if not isinstance(item, dict):\n            return None\n        return item.get('link')\n\n'''
    if marker not in deepbrid:
        raise SystemExit('cloud resolver insertion marker not found')
    deepbrid = deepbrid.replace(marker, insert + marker, 1)

deepbrid_path.write_text(deepbrid, encoding='utf-8')

# --- sources.py ------------------------------------------------------------
sources = sources_path.read_text(encoding='utf-8')
old_list = "internal_scrapers_clouds_list = [('realdebrid', 'rd_cloud', 'rd'), ('premiumize', 'pm_cloud', 'pm'), ('alldebrid', 'ad_cloud', 'ad'),('torbox', 'tb_cloud', 'tb'),('offcloud', 'oc_cloud', 'oc')]"
new_list = "internal_scrapers_clouds_list = [('realdebrid', 'rd_cloud', 'rd'), ('premiumize', 'pm_cloud', 'pm'), ('alldebrid', 'ad_cloud', 'ad'),('torbox', 'tb_cloud', 'tb'),('offcloud', 'oc_cloud', 'oc'),('deepbrid', 'db_cloud', 'deepbrid')]"
if old_list not in sources:
    raise SystemExit('internal cloud scraper list marker not found')
sources = sources.replace(old_list, new_list, 1)

old_active = "active = [i.split('.')[1] for i in settings if getSetting('%s.enabled' % i) == 'true']"
new_active = "active = [i.split('.')[-1] for i in settings if getSetting('%s.enabled' % i) == 'true']"
if old_active not in sources:
    raise SystemExit('internal scraper split marker not found')
sources = sources.replace(old_active, new_active, 1)
sources_path.write_text(sources, encoding='utf-8')

# --- settings.xml ----------------------------------------------------------
settings = settings_path.read_text(encoding='utf-8-sig')
if 'id="db_cloud.enabled"' not in settings:
    start = settings.find('<setting id="deepbrid.priority"')
    if start < 0:
        raise SystemExit('Deepbrid priority setting not found')
    end = settings.find('</setting>', start)
    if end < 0:
        raise SystemExit('Deepbrid priority setting end not found')
    end += len('</setting>')

    block = '''\n\n\t\t\t\t<setting id="db_cloud.enabled" type="boolean" label="32050" help="">\n\t\t\t\t\t<level>0</level>\n\t\t\t\t\t<default>false</default>\n\t\t\t\t\t<dependencies>\n\t\t\t\t\t\t<dependency type="visible">\n\t\t\t\t\t\t\t<and>\n\t\t\t\t\t\t\t\t<condition operator="!is" setting="deepbrid.token"/>\n\t\t\t\t\t\t\t\t<condition operator="is" setting="deepbrid.enable">true</condition>\n\t\t\t\t\t\t\t</and>\n\t\t\t\t\t\t</dependency>\n\t\t\t\t\t</dependencies>\n\t\t\t\t\t<control type="toggle"/>\n\t\t\t\t</setting>'''
    settings = settings[:end] + block + settings[end:]

settings_path.write_text(settings, encoding='utf-8')
