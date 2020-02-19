# -*- coding: utf-8 -*-
#########################################################
# python
import os
import traceback
import subprocess
import json
import time
import random
from datetime import datetime
import platform
# import base64

# third-party
import requests
from sqlitedict import SqliteDict

# sjva 공용
from framework import db, scheduler, app
from framework.util import Util

# 패키지
from .plugin import logger, package_name
from .model import ModelSetting, db_file


#########################################################


class Logic(object):
    # 디폴트 세팅값
    db_default = {
        'use_dht': 'True',
        'scrape': 'False',
        'force_dht': 'False',
        'timeout': '10',
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
            logger.debug('%s plugin_load', package_name)
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
            new_build = int(plugin_info['install'].split('-')[-1].split('.')[0])
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
        try:
            from plugin import plugin_info
            # platform check - whitelist
            if platform.machine() == 'x86_64' and app.config['config']['running_type'] == 'docker':
                tarball = os.path.join(os.path.dirname(__file__), 'install', plugin_info['install'])
                # file existence  check
                if not os.path.isfile(tarball):
                    return {'success': False, 'log': '파일이 없습니다. {}'.format(os.path.basename(tarball))}
                returncode = subprocess.check_call(['tar', '-zxf', tarball, '-C', '/'])
                # tar command check
                if returncode != 0:
                    return {'success': False, 'log': '설치 중 에러 발생 exitcode: {}'.format(returncode)}

                # finally check libtorrent imported
                lt_ver = Logic.is_installed()
                if lt_ver:
                    # 현재 설치된 빌드 번호 업데이트
                    ModelSetting.set('libtorrent_build', plugin_info['install'].split('-')[-1].split('.')[0])
                    return {'success': True, 'log': 'libtorrent v{}'.format(lt_ver)}
                else:
                    return {'success': False, 'log': '설치 후 알수없는 에러. 개발자에게 보고바람'}
            else:
                return {'succes': False, 'log': '지원하지 않는 시스템입니다.'}
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return {'success': False, 'log': str(e)}

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
            'info_hash': str(torrent_info.info_hash()),  # original type: libtorrent.sha1_hash
            'num_pieces': torrent_info.num_pieces(),
            'creator': torrent_info.creator() if torrent_info.creator() else 'libtorrent v{}'.format(lt.version),
            'comment': torrent_info.comment(),
            'files': [{'path': file.path, 'size': file.size} for file in torrent_info.files()],
            'magnet_uri': lt.make_magnet_uri(torrent_info),
        }

    @staticmethod
    def parse_magnet_uri(magnet_uri, scrape=False, use_dht=True, force_dht=False, timeout=10, trackers=None,
                         no_cache=False, n_try=3):
        try:
            import libtorrent as lt
        except ImportError:
            raise ImportError('libtorrent package required')

        # parameters
        params = lt.parse_magnet_uri(magnet_uri)

        lt_version = [int(v) for v in lt.version.split('.')]
        if [0, 16, 13, 0] < lt_version < [1, 1, 3, 0]:
            # for some reason the info_hash needs to be bytes but it's a struct called sha1_hash
            if type({}) == type(params):
                params['info_hash'] = params['info_hash'].to_bytes()
            else:
                params.info_hash = params.info_hash.to_bytes()

        # 캐시에 있으면 ...
        info_hash_from_magnet = str(params['info_hash'] if type({}) == type(params) else params.info_hash)
        if (not no_cache) and (info_hash_from_magnet in Logic.torrent_cache):
            return Logic.torrent_cache[info_hash_from_magnet]['info']

        # add trackers
        if type({}) == type(params):
            if len(params['trackers']) == 0:
                if trackers is None:
                    trackers = json.loads(ModelSetting.get('trackers'))
                params['trackers'] = random.sample(trackers, 5)
        else:
            if len(params.trackers) == 0:
                if trackers is None:
                    trackers = json.loads(ModelSetting.get('trackers'))
                params.trackers = random.sample(trackers, 5)

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

        if force_dht:
            handle.force_dht_announce()

        for tryid in range(max(n_try,1)):
            timeout_value = timeout
            while not handle.has_metadata():
                time.sleep(0.1)
                timeout_value -= 0.1
                if timeout_value <= 0:
                    logger.debug('Failed to get metadata on trial: {}/{}'.format(tryid+1, n_try))
                    break

            if handle.has_metadata():
                lt_info = handle.get_torrent_info()
                logger.debug('Successfully get metadata after {} seconds on trial {}'.format(timeout - timeout_value, tryid+1))
                break
            else:
                if tryid+1 == max(n_try,1):
                    session.remove_torrent(handle, True)
                    raise Exception('Timed out after {}x{} seconds trying to get metainfo'.format(timeout, n_try))

        # create torrent object and generate file stream
        torrent = lt.create_torrent(lt_info)
        torrent.set_creator('libtorrent v{}'.format(lt.version))    # signature
        torrent_dict = torrent.generate()
        # torrent_file = lt.bencode(torrent_dict)

        torrent_info = Logic.convert_torrent_info(lt_info)
        torrent_info.update({
            'trackers': params.trackers if type({}) != type(params) else params['trackers'],
            'creation_date': datetime.fromtimestamp(torrent_dict[b'creation date']).isoformat(),
            'time': {'total': timeout - timeout_value, 'metadata': timeout - timeout_value},
        })

        if scrape:
            # start scraping
            timeout_value = timeout
            while handle.status(0).num_complete < 0:
                time.sleep(0.1)
                timeout_value -= 0.1
                if timeout_value <= 0:
                    logger.error('Timed out after {} seconds trying to get peer info'.format(timeout))

            if handle.status(0).num_complete >= 0:
                torrent_status = handle.status(0)
                
                torrent_info.update({
                    'seeders': torrent_status.num_complete,
                    'peers': torrent_status.num_incomplete,
                })
                torrent_info['time']['scrape'] = timeout - timeout_value
                torrent_info['time']['total'] = torrent_info['time']['metadata'] + torrent_info['time']['scrape']

        session.remove_torrent(handle, True)

        # caching for later use
        if Logic.torrent_cache is None:
            Logic.cache_init()
        Logic.torrent_cache[torrent_info['info_hash']] = {
            # 'file': base64.b64encode(torrent_file),
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
        if Logic.torrent_cache is None:
            Logic.cache_init()
        Logic.torrent_cache[torrent_info['info_hash']] = {
            # 'file': base64.b64encode(torrent_file),
            'info': torrent_info,
        }
        return torrent_info

    @staticmethod
    def parse_torrent_url(url):
        return Logic.parse_torrent_file(requests.get(url).content)
