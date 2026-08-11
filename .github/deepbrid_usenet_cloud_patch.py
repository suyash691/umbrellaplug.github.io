from pathlib import Path

DEEPBRID = Path('omega/plugin.video.umbrella/resources/lib/debrid/deepbrid.py')
NAVIGATOR = Path('omega/plugin.video.umbrella/resources/lib/menus/navigator.py')
ROUTER = Path('omega/plugin.video.umbrella/resources/lib/modules/router.py')


def replace_once(text, old, new, label):
    count = text.count(old)
    assert count == 1, '%s: expected 1 match, got %s' % (label, count)
    return text.replace(old, new, 1)


deepbrid = DEEPBRID.read_text(encoding='utf-8')
navigator = NAVIGATOR.read_text(encoding='utf-8')
router = ROUTER.read_text(encoding='utf-8')

# Include m2ts in the lightweight filename-only checks used by cloud/Usenet.
deepbrid = replace_once(
    deepbrid,
    "VIDEO_EXTENSIONS = (\n    '.mkv', '.mp4', '.avi', '.mov', '.m4v',\n    '.ts', '.wmv', '.mpg', '.mpeg', '.webm'\n)",
    "VIDEO_EXTENSIONS = (\n    '.mkv', '.mp4', '.avi', '.mov', '.m4v',\n    '.ts', '.m2ts', '.wmv', '.mpg', '.mpeg', '.webm'\n)",
    'video extensions'
)

# Add a batch filename probe for read-only torrent cloud browsing. It deliberately
# does not follow redirects; the caller refreshes Deepbrid's one-time links before
# exposing anything for playback.
probe_anchor = "    def _find_episode_file(self, links, season, episode):\n"
probe_helper = '''    def _probe_torrent_link_names(self, links):
        if not links:
            return []

        results = []
        workers = min(8, len(links))

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    self._probe_torrent_link_name,
                    link,
                    index
                ): index
                for index, link in enumerate(links)
            }

            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception as e:
                    log_utils.log(
                        'Deepbrid cloud probe failed: index=%s error=%s' % (
                            futures[future],
                            str(e)
                        ),
                        level=log_utils.LOGWARNING
                    )

        results.sort(key=lambda item: item.get('index', 0))
        return results

'''
assert deepbrid.count(probe_anchor) == 1
deepbrid = deepbrid.replace(probe_anchor, probe_helper + probe_anchor, 1)

usenet_start = deepbrid.index('    # -------------------------------------------------\n    # Usenet\n')
delete_start = deepbrid.index('    # -------------------------------------------------\n    # Delete operations\n', usenet_start)

usenet_cloud_block = '''    # -------------------------------------------------
    # Usenet
    # -------------------------------------------------

    def add_usenet(
        self,
        nzb_url=None,
        nzb_file=None
    ):
        if not self.api_key:
            return None

        result = None

        if nzb_url:
            nzb_url = str(nzb_url).strip()
            if not nzb_url.lower().startswith(('http://', 'https://')):
                return None
            result = self._post(
                'usenet/add',
                data={'nzb_url': nzb_url}
            )

        elif nzb_file:
            try:
                with open(nzb_file, 'rb') as file_handle:
                    result = self._post(
                        'usenet/add',
                        files={'nzb_file': file_handle}
                    )
            except Exception:
                log_utils.error()
                return None

        log_utils.log(
            'Deepbrid add Usenet response: %s' % repr(result),
            level=log_utils.LOGDEBUG
        )

        if not isinstance(result, dict):
            return None

        error = result.get('error')
        if error not in (None, 0, '0', False):
            return None

        return result

    def usenet_uploads(self):
        result = self._get('usenet/uploads')

        if not isinstance(result, dict):
            return []

        error = result.get('error')
        if error not in (None, 0, '0', False):
            return []

        items = result.get('items') or result.get('data') or []
        return [item for item in items if isinstance(item, dict)]

    def usenet_info(self, upload_id):
        if upload_id in (None, ''):
            return {}

        result = self._get(
            'usenet/uploads/info',
            params={'id': upload_id}
        )

        return result if isinstance(result, dict) else {}

    def user_cloud_usenet(self, request_id=None):
        if request_id:
            return self.usenet_info(request_id)

        return {'items': self.usenet_uploads()}

    def unrestrict_usenet(self, file_link_or_id):
        if not file_link_or_id:
            return None

        if str(file_link_or_id).startswith(('http://', 'https://')):
            return file_link_or_id

        return None

    @staticmethod
    def _usenet_upload_id(result):
        if not isinstance(result, dict):
            return None

        upload_id = result.get('id') or result.get('upload_id')
        if upload_id:
            return str(upload_id)

        data = result.get('data')
        if isinstance(data, dict):
            upload_id = data.get('id') or data.get('upload_id')
            if upload_id:
                return str(upload_id)

        return None

    def _recover_usenet_upload_id(self, before, nzb_url=None):
        before_ids = {
            str(item.get('id'))
            for item in (before or [])
            if item.get('id') is not None
        }

        for attempt in range(4):
            if attempt:
                time.sleep(1)

            uploads = self.usenet_uploads()
            new_items = [
                item for item in uploads
                if item.get('id') is not None
                and str(item.get('id')) not in before_ids
            ]

            if len(new_items) == 1:
                return str(new_items[0].get('id'))

            if nzb_url:
                exact = [
                    item for item in uploads
                    if str(item.get('source_url') or '').strip() == nzb_url
                ]
                if len(exact) == 1:
                    return str(exact[0].get('id'))

        return None

    def _select_usenet_file(
        self,
        files,
        title=None,
        season=None,
        episode=None
    ):
        videos = []

        for item in files or []:
            if not isinstance(item, dict):
                continue

            name = item.get('name') or item.get('filename') or ''
            link = item.get('link') or ''
            if not link or not self._is_video_link(link, name):
                continue

            try:
                size = int(item.get('size') or 0)
            except Exception:
                size = 0

            videos.append({
                'name': name,
                'link': link,
                'size': size
            })

        if not videos:
            return None

        is_episode = (
            season not in (None, '')
            and episode not in (None, '')
        )

        if is_episode:
            matches = [
                item for item in videos
                if item.get('name')
                and seas_ep_filter(season, episode, item.get('name'))
            ]

            if not matches:
                log_utils.log(
                    'Deepbrid Usenet: no file matched S%sE%s' % (
                        str(season).zfill(2),
                        str(episode).zfill(2)
                    ),
                    level=log_utils.LOGWARNING
                )
                return None

            matches.sort(key=lambda item: item.get('size', 0), reverse=True)
            selected = matches[0]
        else:
            title_lower = (title or '').lower()
            extras = tuple(
                extra for extra in extras_filter()
                if extra not in title_lower
            )
            filtered = [
                item for item in videos
                if not any(
                    extra in (item.get('name') or '').lower()
                    for extra in extras
                )
            ]
            pool = filtered or videos
            pool.sort(key=lambda item: item.get('size', 0), reverse=True)
            selected = pool[0]

        log_utils.log(
            'Deepbrid Usenet selected file: %s' % repr(selected),
            level=log_utils.LOGDEBUG
        )
        return selected

    def resolve_usenet(
        self,
        nzb_url,
        title=None,
        season=None,
        episode=None
    ):
        if not self.api_key or not nzb_url:
            return None

        nzb_url = str(nzb_url).strip()
        before = self.usenet_uploads()
        added = self.add_usenet(nzb_url=nzb_url)

        if not added:
            return None

        upload_id = self._usenet_upload_id(added)
        if not upload_id:
            upload_id = self._recover_usenet_upload_id(
                before,
                nzb_url=nzb_url
            )

        if not upload_id:
            log_utils.log(
                'Deepbrid Usenet: accepted upload but could not recover ID',
                level=log_utils.LOGWARNING
            )
            return None

        deadline = time.monotonic() + 120.0
        last_file_count = 0

        while time.monotonic() < deadline:
            if control.monitor.abortRequested():
                return None

            remaining = deadline - time.monotonic()
            info = self._get(
                'usenet/uploads/info',
                params={'id': upload_id},
                silent=True,
                timeout=max(1.0, min(self.timeout, remaining))
            )

            if isinstance(info, dict):
                error = info.get('error')
                if error in (None, 0, '0', False):
                    files = info.get('files') or []
                    last_file_count = len(files)
                    selected = self._select_usenet_file(
                        files,
                        title=title,
                        season=season,
                        episode=episode
                    )
                    if selected:
                        return selected.get('link')
                elif error not in (1, '1'):
                    log_utils.log(
                        'Deepbrid Usenet info error: %s' % repr(info),
                        level=log_utils.LOGWARNING
                    )
                    return None

            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(2.0, remaining))

        log_utils.log(
            'Deepbrid Usenet timed out: id=%s files=%s' % (
                upload_id,
                last_file_count
            ),
            level=log_utils.LOGWARNING
        )
        return None

    def add_usenet_url_dialog(self):
        nzb_url = control.dialog.input(
            'Deepbrid NZB URL',
            type=control.alpha_input
        )

        if not nzb_url:
            return

        nzb_url = nzb_url.strip()
        if not nzb_url.lower().startswith(('http://', 'https://')):
            return control.notification(
                title=self.name,
                message='Please enter a valid NZB URL',
                icon='ERROR'
            )

        before = self.usenet_uploads()
        result = self.add_usenet(nzb_url=nzb_url)
        if not result:
            return control.notification(
                title=self.name,
                message='NZB could not be added',
                icon='ERROR'
            )

        upload_id = self._usenet_upload_id(result)
        if not upload_id:
            upload_id = self._recover_usenet_upload_id(before, nzb_url=nzb_url)

        message = 'NZB added to Deepbrid'
        if upload_id:
            message += ' (ID %s)' % upload_id

        control.notification(title=self.name, message=message)
        control.refresh()
        return True

    # -------------------------------------------------
    # Cloud (read-only)
    # -------------------------------------------------

    def user_cloud(self, request_id=None):
        if request_id:
            return self.torrent_info(request_id)

        return self.torrent_info()

    @staticmethod
    def _cloud_sort_id(item):
        try:
            return int(item.get('id') or 0)
        except Exception:
            return 0

    def _cloud_listitem_art(self, listitem):
        listitem.setArt({
            'icon': deepbrid_icon,
            'poster': deepbrid_icon,
            'thumb': deepbrid_icon,
            'fanart': addon_fanart,
            'banner': deepbrid_icon
        })

    def user_cloud_to_listItem(self, folder_id=None):
        try:
            syshandle = int(argv[1])
        except Exception:
            return

        torrents = self._torrent_list()
        uploads = self.usenet_uploads()
        sysaddon = 'plugin://plugin.video.umbrella/'

        categories = [
            (
                'Torrent Cloud (%s)' % len(torrents),
                '%s?action=db_CloudTorrents' % sysaddon
            ),
            (
                'Usenet Uploads (%s)' % len(uploads),
                '%s?action=db_CloudUsenet' % sysaddon
            )
        ]

        for label, item_url in categories:
            listitem = control.item(label=label, offscreen=True)
            self._cloud_listitem_art(listitem)
            control.set_info(listitem, {'title': label})
            control.addItem(
                handle=syshandle,
                url=item_url,
                listitem=listitem,
                isFolder=True
            )

        control.content(syshandle, 'files')
        control.directory(syshandle, cacheToDisc=False)

    def cloud_torrents_to_listitem(self):
        try:
            syshandle = int(argv[1])
        except Exception:
            return

        sysaddon = 'plugin://plugin.video.umbrella/'
        torrents = self._torrent_list()
        torrents.sort(key=self._cloud_sort_id, reverse=True)

        for count, item in enumerate(torrents, 1):
            request_id = item.get('id')
            name = item.get('filename') or 'Torrent %s' % request_id
            try:
                progress = int(item.get('progress') or 0)
            except Exception:
                progress = 0
            links = item.get('links') or []
            ready = progress >= 100 and bool(links)
            status = 'Ready' if ready else '%s%%' % progress
            label = '%02d | [B]%s[/B] | %s' % (count, status, name)

            plot = 'Progress: %s%%' % progress
            if item.get('seeders') is not None:
                plot += '[CR]Seeders: %s' % item.get('seeders')
            if item.get('speed'):
                plot += '[CR]Speed: %s' % item.get('speed')
            plot += '[CR]Files: %s' % len(links)

            listitem = control.item(label=label, offscreen=True)
            self._cloud_listitem_art(listitem)
            control.set_info(listitem, {'title': name, 'plot': plot})

            item_url = ''
            if ready and request_id is not None:
                item_url = (
                    '%s?action=db_BrowseCloud&id=%s&mediatype=torrent' %
                    (sysaddon, request_id)
                )

            control.addItem(
                handle=syshandle,
                url=item_url,
                listitem=listitem,
                isFolder=bool(item_url)
            )

        control.content(syshandle, 'files')
        control.directory(syshandle, cacheToDisc=False)

    def cloud_usenet_to_listitem(self):
        try:
            syshandle = int(argv[1])
        except Exception:
            return

        sysaddon = 'plugin://plugin.video.umbrella/'
        uploads = self.usenet_uploads()

        for count, item in enumerate(uploads, 1):
            upload_id = item.get('id')
            title = item.get('title') or 'NZB %s' % upload_id
            source = item.get('source') or 'unknown'
            added_at = item.get('added_at') or ''
            label = '%02d | [B]%s[/B] | %s' % (count, source.capitalize(), title)
            if added_at:
                label += ' | %s' % added_at

            plot = 'Source: %s' % source
            if item.get('source_url'):
                plot += '[CR]Source URL: %s' % item.get('source_url')
            if added_at:
                plot += '[CR]Added: %s' % added_at

            listitem = control.item(label=label, offscreen=True)
            self._cloud_listitem_art(listitem)
            control.set_info(listitem, {'title': title, 'plot': plot})

            item_url = ''
            if upload_id is not None:
                item_url = (
                    '%s?action=db_BrowseCloud&id=%s&mediatype=usenet' %
                    (sysaddon, upload_id)
                )

            control.addItem(
                handle=syshandle,
                url=item_url,
                listitem=listitem,
                isFolder=bool(item_url)
            )

        control.content(syshandle, 'files')
        control.directory(syshandle, cacheToDisc=False)

    def _add_cloud_file_item(
        self,
        syshandle,
        count,
        name,
        direct,
        size_text=''
    ):
        if not direct:
            return

        label = '%02d | [B]FILE[/B]' % count
        if size_text:
            label += ' | %s' % size_text
        label += ' | %s' % name

        listitem = control.item(label=label, offscreen=True)
        self._cloud_listitem_art(listitem)
        control.set_info(
            listitem,
            {
                'title': name,
                'plot': ('Size: %s' % size_text) if size_text else name
            }
        )
        listitem.setProperty('IsPlayable', 'true')
        item_url = (
            'plugin://plugin.video.umbrella/?action=db_PlayDownload&url=%s' %
            quote_plus(direct)
        )
        control.addItem(
            handle=syshandle,
            url=item_url,
            listitem=listitem,
            isFolder=False
        )

    def browse_user_torrents(
        self,
        folder_id,
        mediatype='torrent'
    ):
        try:
            syshandle = int(argv[1])
        except Exception:
            return

        if mediatype == 'usenet':
            info = self.usenet_info(folder_id)
            files = info.get('files') or [] if isinstance(info, dict) else []
            count = 0

            for item in files:
                if not isinstance(item, dict):
                    continue
                name = item.get('name') or item.get('filename') or ''
                direct = item.get('link') or ''
                if not direct or not self._is_video_link(direct, name):
                    continue
                count += 1
                size_text = item.get('size_human') or ''
                if not size_text and item.get('size'):
                    try:
                        size_text = '%.2f GB' % (
                            float(item.get('size')) / 1073741824.0
                        )
                    except Exception:
                        size_text = str(item.get('size'))
                self._add_cloud_file_item(
                    syshandle,
                    count,
                    name or 'Usenet file %s' % count,
                    direct,
                    size_text=size_text
                )

        else:
            info = self.torrent_info(folder_id)
            if not isinstance(info, dict):
                info = {}
            links = info.get('links') or []
            probes = self._probe_torrent_link_names(links)

            if len(links) == 1 and probes and not probes[0].get('filename'):
                probes[0]['filename'] = info.get('filename') or 'Torrent file'

            fresh_info = self.torrent_info(folder_id)
            fresh_links = (
                fresh_info.get('links') or []
                if isinstance(fresh_info, dict)
                else []
            )

            if len(fresh_links) != len(links):
                control.notification(
                    title=self.name,
                    message='Torrent links changed; reopen this folder',
                    icon='WARNING'
                )
                control.directory(syshandle, cacheToDisc=False)
                return

            count = 0
            for probe in probes:
                index = probe.get('index')
                if index is None or index >= len(fresh_links):
                    continue
                name = probe.get('filename') or ''
                if not self._is_video_link('', name):
                    continue
                count += 1
                self._add_cloud_file_item(
                    syshandle,
                    count,
                    name,
                    fresh_links[index]
                )

        control.content(syshandle, 'files')
        control.directory(syshandle, cacheToDisc=False)

'''

deepbrid = deepbrid[:usenet_start] + usenet_cloud_block + deepbrid[delete_start:]

old_service = """\tdef deepbrid_service(self, folderName=''):\n\t\tif self.useContainerTitles: control.setContainerName(folderName)\n\t\tif getSetting('deepbrid.token'):\n\t\t\tself.addDirectoryItem('Deepbrid: Download History', 'db_DownloadHistory&offset=0', 'tools.png', 'DefaultAddonService.png')\n\t\t\tself.addDirectoryItem('Deepbrid: Hoster Limits', 'db_AccountLimits', 'tools.png', 'DefaultAddonService.png', isFolder=False)\n\t\t\tself.addDirectoryItem('Deepbrid: Account Info', 'db_AccountInfo', 'tools.png', 'DefaultAddonService.png', isFolder=False)\n\t\telse:\n\t\t\tself.addDirectoryItem('[I]Please setup in Accounts[/I]', 'tools_openSettings&query=6.0', 'tools.png', 'DefaultAddonService.png', isFolder=False)\n\t\tself.endDirectory()\n"""
new_service = """\tdef deepbrid_service(self, folderName=''):\n\t\tif self.useContainerTitles: control.setContainerName(folderName)\n\t\tif getSetting('deepbrid.token'):\n\t\t\tself.addDirectoryItem('Deepbrid: Cloud Storage (Read-only)', 'db_CloudStorage&folderName=%s' % quote_plus('Deepbrid Cloud'), 'tools.png', 'DefaultAddonService.png')\n\t\t\tself.addDirectoryItem('Deepbrid: Add NZB URL', 'db_AddUsenetUrl', 'tools.png', 'DefaultAddonService.png', isFolder=False)\n\t\t\tself.addDirectoryItem('Deepbrid: Download History', 'db_DownloadHistory&offset=0', 'tools.png', 'DefaultAddonService.png')\n\t\t\tself.addDirectoryItem('Deepbrid: Hoster Limits', 'db_AccountLimits', 'tools.png', 'DefaultAddonService.png', isFolder=False)\n\t\t\tself.addDirectoryItem('Deepbrid: Account Info', 'db_AccountInfo', 'tools.png', 'DefaultAddonService.png', isFolder=False)\n\t\telse:\n\t\t\tself.addDirectoryItem('[I]Please setup in Accounts[/I]', 'tools_openSettings&query=6.0', 'tools.png', 'DefaultAddonService.png', isFolder=False)\n\t\tself.endDirectory()\n"""
navigator = replace_once(navigator, old_service, new_service, 'Deepbrid service menu')

old_router = """\t\telif action == 'db_DownloadHistory':\n\t\t\tfrom resources.lib.debrid.deepbrid import Deepbrid\n\t\t\tDeepbrid().download_history_to_listitem(offset=params.get('offset', '0'))\n\t\telif action == 'db_PlayDownload':\n\t\t\tif url:\n\t\t\t\tcontrol.player.play(url.replace(' ', '%20'))\n"""
new_router = """\t\telif action == 'db_CloudStorage':\n\t\t\tfrom resources.lib.debrid.deepbrid import Deepbrid\n\t\t\tDeepbrid().user_cloud_to_listItem()\n\t\telif action == 'db_CloudTorrents':\n\t\t\tfrom resources.lib.debrid.deepbrid import Deepbrid\n\t\t\tDeepbrid().cloud_torrents_to_listitem()\n\t\telif action == 'db_CloudUsenet':\n\t\t\tfrom resources.lib.debrid.deepbrid import Deepbrid\n\t\t\tDeepbrid().cloud_usenet_to_listitem()\n\t\telif action == 'db_BrowseCloud':\n\t\t\tfrom resources.lib.debrid.deepbrid import Deepbrid\n\t\t\tDeepbrid().browse_user_torrents(params.get('id'), mediatype or 'torrent')\n\t\telif action == 'db_AddUsenetUrl':\n\t\t\tfrom resources.lib.debrid.deepbrid import Deepbrid\n\t\t\tDeepbrid().add_usenet_url_dialog()\n\t\telif action == 'db_DownloadHistory':\n\t\t\tfrom resources.lib.debrid.deepbrid import Deepbrid\n\t\t\tDeepbrid().download_history_to_listitem(offset=params.get('offset', '0'))\n\t\telif action == 'db_PlayDownload':\n\t\t\tif url:\n\t\t\t\tcontrol.player.play(url.replace(' ', '%20'))\n"""
router = replace_once(router, old_router, new_router, 'Deepbrid router actions')

DEEPBRID.write_text(deepbrid, encoding='utf-8')
NAVIGATOR.write_text(navigator, encoding='utf-8')
ROUTER.write_text(router, encoding='utf-8')
