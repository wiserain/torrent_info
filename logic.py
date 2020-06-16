# -*- coding: utf-8 -*-
#########################################################
# python
import os
import sys
import traceback
import subprocess
import json
import time
from datetime import datetime
import platform
import urllib
import tarfile
import tempfile
import shutil

# third-party
import requests
from sqlitedict import SqliteDict

# sjva 공용
from framework import db, scheduler, app
from framework.util import Util

# 패키지
from .plugin import logger, package_name
from .model import ModelSetting, db_file

sys.path.append('/usr/lib/python2.7/site-packages')

#########################################################


class Logic(object):
    # 디폴트 세팅값
    db_default = {
        'use_dht': 'True',
        'scrape': 'False',
        'timeout': '15',
        'trackers': '',
        'n_try': '3',
        'tracker_last_update': '1970-01-01',
        'tracker_update_every': '30',
        'libtorrent_build': '191217',
    }

    torrent_cache = None

    @staticmethod
    def db_init():
        try:
            for key, value in Logic.db_default.items():
                if db.session.query(ModelSetting).filter_by(key=key).count() == 0:
                    db.session.add(ModelSetting(key, value))
            db.session.commit()
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def plugin_load():
        try:
            # DB 초기화
            Logic.db_init()

            # 편의를 위해 json 파일 생성
            from plugin import plugin_info
            Util.save_from_dict_to_json(plugin_info, os.path.join(os.path.dirname(__file__), 'info.json'))

            #
            # 자동시작 옵션이 있으면 보통 여기서
            #
            # 토렌트 캐쉬 초기화
            Logic.cache_init()

            # libtorrent 자동 설치
            new_build = int(plugin_info['install'].split('-')[-1])
            installed_build = ModelSetting.get_int('libtorrent_build')
            if (new_build > installed_build) or (not Logic.is_installed()):
                Logic.install()

            # tracker 자동 업데이트
            tracker_update_every = ModelSetting.get_int('tracker_update_every')
            tracker_last_update = ModelSetting.get('tracker_last_update')
            if tracker_update_every > 0:
                if (datetime.now() - datetime.strptime(tracker_last_update, '%Y-%m-%d')).days >= tracker_update_every:
                    Logic.update_tracker()
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def plugin_unload():
        try:
            logger.debug('%s plugin_unload', package_name)
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def setting_save(req):
        try:
            for key, value in req.form.items():
                logger.debug('Key:%s Value:%s', key, value)
                entity = db.session.query(ModelSetting).filter_by(key=key).with_for_update().first()
                entity.value = value
            db.session.commit()
            return True
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False

    # 기본 구조 End
    ##################################################################

    @staticmethod
    def cache_init():
        if Logic.torrent_cache is None:
            Logic.torrent_cache = SqliteDict(
                db_file, tablename='plugin_{}_cache'.format(package_name), encode=json.dumps, decode=json.loads, autocommit=True
            )

    @staticmethod
    def tracker_save(req):
        for key, value in req.form.items():
            logger.debug({'key': key, 'value': value})
            if key == 'trackers':
                value = json.dumps(value.split('\n'))
            logger.debug('Key:%s Value:%s', key, value)
            entity = db.session.query(ModelSetting).filter_by(key=key).with_for_update().first()
            entity.value = value
        db.session.commit()

    @staticmethod
    def update_tracker():
        # https://github.com/ngosang/trackerslist
        trackers_url_from = 'https://raw.githubusercontent.com/ngosang/trackerslist/master/trackers_best_ip.txt'
        new_trackers = requests.get(trackers_url_from).content.decode('utf8').split('\n\n')[:-1]
        ModelSetting.set('trackers', json.dumps(new_trackers))
        ModelSetting.set('tracker_last_update', datetime.now().strftime('%Y-%m-%d'))

    @staticmethod
    def is_installed():
        try:
            import libtorrent as lt
            return lt.version
        except ImportError:
            return False

    @staticmethod
    def install():
        # platform check - whitelist
        march = platform.machine()
        if app.config['config']['running_type'] == 'docker' and march in ['x86_64', 'aarch64', 'armv7l']:
            from plugin import plugin_info
            lt_tag = plugin_info['install']
            lt_ver, lt_build = lt_tag.split('-')

            tmpdir = tempfile.mkdtemp()

            # download libtorrent
            if march == 'x86_64':
                darch = 'amd64'
            elif march == 'aarch64':
                darch = 'arm64'
            elif march == 'armv7l':
                darch = 'arm'
            url_base = 'https://github.com/wiserain/docker-libtorrent/releases/download/{}/'.format(lt_tag)
            filename = 'libtorrent-{}-alpine3.10-py2-{}.tar.gz'.format(lt_ver, darch)
            try:
                urllib.urlretrieve(url_base + filename, filename=os.path.join(tmpdir, filename))
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                shutil.rmtree(tmpdir)
                return {'success': False, 'log': 'libtorrent 다운로드 에러: ' + str(e)}
            
            # download apks
            exitcode = subprocess.check_call(['apk', 'fetch', '-q', '--no-cache', '-o', tmpdir, 'libstdc++', 'boost-python2', 'boost-system'])
            if exitcode != 0:
                shutil.rmtree(tmpdir)
                return {'success': False, 'log': 'apk 다운로드 에러 exitcode: {}'.format(exitcode)}

            # installing
            for filename in os.listdir(tmpdir):
                try:
                    tar = tarfile.open(os.path.join(tmpdir, filename))
                    tar.extractall('/', members=[x for x in tar.getmembers() if x.name.startswith('usr')])
                    tar.close()
                except Exception as e:
                    logger.error('Exception:%s', e)
                    logger.error(traceback.format_exc())
                    shutil.rmtree(tmpdir)
                    return {'success': False, 'log': '{} 설치 중 에러: {}'.format(filename, str(e))}

            shutil.rmtree(tmpdir)

            # finally check libtorrent imported
            lt_ver = Logic.is_installed()
            if lt_ver:
                # 현재 설치된 빌드 번호 업데이트
                ModelSetting.set('libtorrent_build', lt_build)
                return {'success': True, 'log': 'libtorrent v{}'.format(lt_ver)}
            else:
                return {'success': False, 'log': 'libtorrent 불러올 수 없음. 개발자에게 보고바람'}
        else:
            return {'succes': False, 'log': '지원하지 않는 시스템입니다.'}

    @staticmethod
    def size_fmt(num, suffix='B'):
        # Windows에서 쓰는 단위로 가자 https://superuser.com/a/938259
        for unit in ['','K','M','G','T','P','E','Z']:
            if abs(num) < 1000.0:
                return "%3.1f %s%s" % (num, unit, suffix)
            num /= 1024.0
        return "%.1f %s%s" % (num, 'Y', suffix)

    @staticmethod
    def convert_torrent_info(torrent_info):
        """from libtorrent torrent_info to python dictionary object"""
        try:
            import libtorrent as lt
        except ImportError:
            raise ImportError('libtorrent package required')

        return {
            'name': torrent_info.name(),
            'num_files': torrent_info.num_files(),
            'total_size': torrent_info.total_size(),  # in byte
            'total_size_fmt': Logic.size_fmt(torrent_info.total_size()),  # in byte
            'info_hash': str(torrent_info.info_hash()),  # original type: libtorrent.sha1_hash
            'num_pieces': torrent_info.num_pieces(),
            'creator': torrent_info.creator() if torrent_info.creator() else 'libtorrent v{}'.format(lt.version),
            'comment': torrent_info.comment(),
            'files': [{'path': file.path, 'size': file.size, 'size_fmt': Logic.size_fmt(file.size)} for file in torrent_info.files()],
            'magnet_uri': lt.make_magnet_uri(torrent_info),
        }

    @staticmethod
    def parse_magnet_uri(magnet_uri, scrape=None, use_dht=None, timeout=None, trackers=None, no_cache=None, n_try=None):
        try:
            import libtorrent as lt
        except ImportError:
            raise ImportError('libtorrent package required')

        # default function arguments from db
        if scrape is None:
            scrape = ModelSetting.get_bool('scrape')
        if use_dht is None:
            use_dht = ModelSetting.get_bool('use_dht')
        if timeout is None:
            timeout = ModelSetting.get_int('timeout')
        if trackers is None:
            trackers = json.loads(ModelSetting.get('trackers'))
        if n_try is None:
            n_try = ModelSetting.get_int('n_try')
        if no_cache is None:
            no_cache = False

        # parameters
        params = lt.parse_magnet_uri(magnet_uri)

        # prevent downloading
        # https://stackoverflow.com/q/45680113
        if isinstance(params, dict):
            params['flags'] |= lt.add_torrent_params_flags_t.flag_upload_mode
        else:
            params.flags |= lt.add_torrent_params_flags_t.flag_upload_mode

        lt_version = [int(v) for v in lt.version.split('.')]
        if [0, 16, 13, 0] < lt_version < [1, 1, 3, 0]:
            # for some reason the info_hash needs to be bytes but it's a struct called sha1_hash
            if type({}) == type(params):
                params['info_hash'] = params['info_hash'].to_bytes()
            else:
                params.info_hash = params.info_hash.to_bytes()

        # 캐시에 있으면 ...
        info_hash_from_magnet = str(params['info_hash'] if type({}) == type(params) else params.info_hash)
        Logic.cache_init()
        if (not no_cache) and (info_hash_from_magnet in Logic.torrent_cache):
            return Logic.torrent_cache[info_hash_from_magnet]['info']

        # add trackers
        if type({}) == type(params):
            if len(params['trackers']) == 0:
                params['trackers'] = trackers
        else:
            if len(params.trackers) == 0:
                params.trackers = trackers

        # session
        session = lt.session()

        session.listen_on(6881, 6891)

        session.add_extension('ut_metadata')
        session.add_extension('ut_pex')
        session.add_extension('metadata_transfer')

        if use_dht:
            session.add_dht_router('router.utorrent.com', 6881)
            session.add_dht_router('router.bittorrent.com', 6881)
            session.add_dht_router("dht.transmissionbt.com", 6881)
            session.add_dht_router('127.0.0.1', 6881)
            session.start_dht()

        # handle
        handle = session.add_torrent(params)

        if use_dht:
            handle.force_dht_announce()

        max_try = max(n_try,1)
        for tryid in range(max_try):
            timeout_value = timeout
            logger.debug('Trying to get metadata ... {}/{}'.format(tryid+1, max_try))
            while not handle.has_metadata():
                time.sleep(0.1)
                timeout_value -= 0.1
                if timeout_value <= 0:
                    break

            if handle.has_metadata():
                lt_info = handle.get_torrent_info()
                logger.debug('Successfully got metadata after {}*{}+{} seconds'.format(tryid, timeout, timeout - timeout_value))
                time_metadata = tryid * timeout + (timeout - timeout_value)
                break
            else:
                if tryid+1 == max_try:
                    session.remove_torrent(handle, True)
                    raise Exception('Timed out after {}*{} seconds'.format(max_try, timeout))

        # create torrent object and generate file stream
        torrent = lt.create_torrent(lt_info)
        torrent.set_creator('libtorrent v{}'.format(lt.version))    # signature
        torrent_dict = torrent.generate()

        torrent_info = Logic.convert_torrent_info(lt_info)
        torrent_info.update({
            'trackers': params.trackers if type({}) != type(params) else params['trackers'],
            'creation_date': datetime.fromtimestamp(torrent_dict[b'creation date']).isoformat(),
            'time': {'total': time_metadata, 'metadata': time_metadata},
        })

        if scrape:
            # start scraping
            for tryid in range(max_try):
                timeout_value = timeout
                logger.debug('Trying to get peerinfo ... {}/{}'.format(tryid+1, max_try))
                while handle.status(0).num_complete < 0:
                    time.sleep(0.1)
                    timeout_value -= 0.1
                    if timeout_value <= 0:
                        break

                if handle.status(0).num_complete >= 0:
                    torrent_status = handle.status(0)
                    logger.debug('Successfully got peerinfo after {}*{}+{} seconds'.format(tryid, timeout, timeout - timeout_value))
                    time_scrape = tryid * timeout + (timeout - timeout_value)
                    
                    torrent_info.update({
                        'seeders': torrent_status.num_complete,
                        'peers': torrent_status.num_incomplete,
                    })
                    torrent_info['time']['scrape'] = time_scrape
                    torrent_info['time']['total'] = torrent_info['time']['metadata'] + torrent_info['time']['scrape']
                    break
                else:
                    if tryid+1 == max_try:
                        logger.error('Timed out after {}*{} seconds'.format(max_try, timeout))

        session.remove_torrent(handle, True)

        # caching for later use
        Logic.torrent_cache[torrent_info['info_hash']] = {
            'info': torrent_info,
        }
        return torrent_info

    @staticmethod
    def parse_torrent_file(torrent_file):
        # torrent_file >> torrent_dict >> lt_info >> torrent_info
        try:
            import libtorrent as lt
        except ImportError:
            raise ImportError('libtorrent package required')
        
        torrent_dict = lt.bdecode(torrent_file)
        lt_info = lt.torrent_info(torrent_dict)
        torrent_info = Logic.convert_torrent_info(lt_info)
        if b'announce-list' in torrent_dict:
            torrent_info.update({'trackers': [x.decode('utf-8') for x in torrent_dict[b'announce-list'][0]]})
        torrent_info.update({'creation_date': datetime.fromtimestamp(torrent_dict[b'creation date']).isoformat()})

        # caching for later use
        Logic.cache_init()
        Logic.torrent_cache[torrent_info['info_hash']] = {
            'info': torrent_info,
        }
        return torrent_info

    @staticmethod
    def parse_torrent_url(url):
        return Logic.parse_torrent_file(requests.get(url).content)
