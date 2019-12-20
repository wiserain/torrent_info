# -*- coding: utf-8 -*-
#########################################################
# python
import os
import sys
import traceback
from datetime import datetime, timedelta
import logging
import subprocess
import json
import time
import random
from collections import OrderedDict

# third-party

# sjva 공용
from framework import db, scheduler, app
from framework.job import Job
from framework.util import Util

# 패키지
from .plugin import logger, package_name
from .model import ModelSetting
#########################################################



class LimitedSizeDict(OrderedDict):
    def __init__(self, *args, **kwds):
        self.size = kwds.pop('size', None)
        OrderedDict.__init__(self, *args, **kwds)
        self._limit_size()

    def __setitem__(self, key, value):
        OrderedDict.__setitem__(self, key, value)
        self._limit_size()

    def _limit_size(self):
        if self.size is not None:
            while len(self) > self.size:
                self.popitem(last=False)

    def sizeto(self, new_size):
        self.size = new_size
        self._limit_size()


class Logic(object):
    # 디폴트 세팅값
    db_default = {
        'auto_start': 'False',
        'scrape': 'False',
        'use_dht': 'True',
        'force_dht': 'False',
        'timeout': '30',
        'trackers': json.dumps([
            'udp://62.138.0.158:6969/announce',
            'udp://188.241.58.209:6969/announce',
            'udp://93.158.213.92:1337/announce',
            'udp://151.80.120.113:2710/announce',
            'udp://151.80.120.112:2710/announce',
            'udp://208.83.20.20:6969/announce',
            'udp://185.19.107.254:80/announce',
            'udp://5.206.19.247:6969/announce',
            'udp://37.235.174.46:2710/announce',
            'udp://89.234.156.205:451/announce',
            'udp://45.56.74.11:6969/announce',
            'udp://54.37.235.149:6969/announce',
            'udp://212.1.226.176:2710/announce',
            'udp://159.100.245.181:6969/announce',
            'udp://51.15.226.113:6969/announce',
            'udp://185.181.60.67:80/announce',
            'udp://142.44.243.4:1337/announce',
            'udp://51.15.40.114:80/announce',
            'udp://176.113.71.19:6961/announce',
            'udp://184.105.151.164:6969/announce',
        ]),
        'cache_size': '10'
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
            # 토렌트 캐쉬
            Logic.torrent_cache = LimitedSizeDict(size=ModelSetting.get_int('cache_size'))

            # libtorrent 자동 설치
            if not Logic.is_installed():
                Logic.install()
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
            # cache size도 변경해줘야...
            Logic.torrent_cache.sizeto(ModelSetting.get_int('cache_size'))
            return True
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False

    # 기본 구조 End
    ##################################################################

    @staticmethod
    def is_installed():
        try:
            import libtorrent as lt
            return lt.version
        except ImportError:
            return False

    @staticmethod
    def install():
        ret = {}
        try:
            import platform
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
                    ret['success'] = True
                    ret['log'] = 'libtorrent v{}'.format(lt_ver)
                else:
                    ret['success'] = False
                    ret['log'] = '설치 후 알수없는 에러. 개발자에게 보고바람'
            else:
                ret['success'] = False
                ret['log'] = '지원하지 않는 시스템입니다.'
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            ret['success'] = False
            ret['log'] = str(e)
        return ret

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
            'total_size': torrent_info.total_size(),    # in byte
            'info_hash': str(torrent_info.info_hash()), # original type: libtorrent.sha1_hash
            'num_pieces': torrent_info.num_pieces(),
            'creator': torrent_info.creator(),
            'comment': torrent_info.comment(),
            'files': [{'path': file.path, 'size': file.size} for file in torrent_info.files()],
            'magnet_uri': lt.make_magnet_uri(torrent_info),
        }

    @staticmethod            
    def parse_magnet_uri(magnet_uri, scrape=False, use_dht=True, force_dht=False, timeout=30, trackers=None, no_cache=False):
        try:
            import libtorrent as lt
        except ImportError:
            raise ImportError('libtorrent package required')

        # parameters
        params = lt.parse_magnet_uri(magnet_uri)

        lt_version = [int(v) for v in lt.version.split('.')]
        if [0, 16, 13, 0] < lt_version < [1, 1, 3, 0]:
            # for some reason the info_hash needs to be bytes but it's a struct called sha1_hash
            if type(params) == type({}):
                params['info_hash'] = params['info_hash'].to_bytes()
            else:
                params.info_hash = params.info_hash.to_bytes()

        # add trackers
        if type(params) == type({}):
            if len(params['trackers']) == 0:
                if trackers is None:
                    trackers = json.loads(ModelSetting.get('trackers'))
                params['trackers'] = random.sample(trackers, 5)
        else:
            if len(params.trackers) == 0:
                if trackers is None:
                    trackers = json.loads(ModelSetting.get('trackers'))
                params.trackers = random.sample(trackers, 5)
        
        # 캐시에 있으면 ...
        info_hash_from_magnet = str(params['info_hash'] if type(params) == type({}) else params.info_hash)
        if (info_hash_from_magnet in Logic.torrent_cache) and not no_cache:
            return Logic.torrent_cache[info_hash_from_magnet]['info']

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

        timeout_value = timeout
        while not handle.has_metadata():
            time.sleep(0.1)
            timeout_value -= 0.1
            if timeout_value <= 0:
                session.remove_torrent(handle, True)
                raise Exception('Timed out after {} seconds trying to get metainfo'.format(timeout))

        lt_info = handle.get_torrent_info()

        # create torrent object and generate file stream
        torrent = lt.create_torrent(lt_info)
        torrent_dict = torrent.generate()
        torrent_file = lt.bencode(torrent_dict)

        torrent_info = Logic.convert_torrent_info(lt_info)
        torrent_info.update({
            'trackers': params.trackers if type(params) != type({}) else params['trackers'],
            'creation_date': datetime.fromtimestamp(torrent_dict[b'creation date']).isoformat(),    # TODO: localtime?
            'time_metadata': timeout - timeout_value,
        })

        if scrape:
            # start scraping
            timeout_value = timeout
            while handle.status(0).num_complete < 0:
                time.sleep(0.1)
                timeout_value -= 0.1
                if timeout_value <= 0:
                    session.remove_torrent(handle, True)
                    raise Exception('Timed out after {} seconds trying to get peer info'.format(timeout))

            torrent_status = handle.status(0)

            torrent_info.update({
                'seeders': torrent_status.num_complete,
                'peers': torrent_status.num_incomplete,
                'time_scrape': timeout - timeout_value,
            })
            
        session.remove_torrent(handle, True)

        # caching for later use
        Logic.torrent_cache[torrent_info['info_hash']] = {
            'name': torrent_info['name'],
            'file': torrent_file,
            'info': torrent_info
        }
        return torrent_info

    @staticmethod
    def parse_torrent_file(torrent_file):
        try:
            import libtorrent as lt
        except ImportError:
            raise ImportError('libtorrent package required')
        torrent_dict = lt.bdecode(torrent_file)
        lt_info = lt.torrent_info(torrent_dict)
        torrent_info = Logic.convert_torrent_info(lt_info)
        if b'announce-list' in torrent_dict:
            torrent_info.update({'trackers': [x.decode('utf-8') for x in torrent_dict[b'announce-list'][0]]})
        torrent_info.update({'creation_date': datetime.fromtimestamp(torrent_dict[b'creation date'])})

        # caching for later use
        Logic.torrent_cache[torrent_info['info_hash']] = {
            'name': torrent_info['name'],
            'file': torrent_file,
            'info': torrent_info
        }
        return torrent_info

    @staticmethod
    def parse_torrent_url(url):
        import requests
        return Logic.parse_torrent_file(requests.get(url).content)
