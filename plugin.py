# -*- coding: utf-8 -*-
#########################################################
# 고정영역
#########################################################
# python
import os
import traceback
import json
from urllib import quote
import base64

# third-party
from flask import Blueprint, request, render_template, redirect, jsonify, Response
from flask_login import login_required
import requests

# sjva 공용
from framework.logger import get_logger
from framework import app, db, scheduler

# 패키지
package_name = __name__.split('.')[0]
logger = get_logger(package_name)

from logic import Logic
from model import ModelSetting

blueprint = Blueprint(
    package_name, package_name,
    url_prefix='/%s' % package_name,
    template_folder=os.path.join(os.path.dirname(__file__), 'templates')
)


def plugin_load():
    Logic.plugin_load()


def plugin_unload():
    Logic.plugin_unload()


plugin_info = {
    "category_name": "torrent",
    "version": "0.0.1.4",
    "name": "torrent_info",
    "home": "https://github.com/wiserain/torrent_info",
    "more": "https://github.com/wiserain/torrent_info",
    "description": "토렌트 마그넷/파일 정보를 보여주는 플러그인",
    "developer": "wiserain",
    "zip": "https://github.com/wiserain/torrent_info/archive/master.zip",
    "icon": "",
    "install": "libtorrent-1.2.4-200211.tar.gz",
}
#########################################################


# 메뉴 구성.
menu = {
    'main': [package_name, '토렌트 정보'],
    'sub': [
        ['setting', '설정'], ['search', '검색'], ['log', '로그']
    ],
    'category': 'torrent',
}


#########################################################
# WEB Menu
#########################################################
@blueprint.route('/')
def home():
    return redirect('/%s/search' % package_name)


@blueprint.route('/<sub>')
@login_required
def detail(sub):
    logger.debug('menu %s %s', package_name, sub)
    if sub == 'setting':
        arg = ModelSetting.to_dict()
        arg['trackers'] = '\n'.join(json.loads(arg['trackers']))
        arg['plugin_ver'] = plugin_info['version']
        return render_template('%s_setting.html' % package_name, sub=sub, arg=arg)
    elif sub == 'search':
        arg = ModelSetting.to_dict()
        return render_template('%s_search.html' % package_name, arg=arg)
    elif sub == 'log':
        return render_template('log.html', package=package_name)
    return render_template('sample.html', title='%s - %s' % (package_name, sub))


#########################################################
# For UI                                                          
#########################################################
@blueprint.route('/ajax/<sub>', methods=['GET', 'POST'])
def ajax(sub):
    logger.debug('AJAX %s %s', package_name, sub)
    # 설정 저장
    if sub == 'setting_save':
        try:
            ret = Logic.setting_save(request)
            return jsonify(ret)
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
    elif sub == 'install':
        try:
            ret = Logic.install()
            return jsonify(ret)
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
    elif sub == 'is_installed':
        try:
            is_installed = Logic.is_installed()
            if is_installed:
                ret = {'installed': True, 'version': is_installed}
            else:
                ret = {'installed': False}
            return jsonify(ret)
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
    elif sub == 'cache':
        try:
            if request.form.get('clear', False):
                Logic.torrent_cache.clear()
            return jsonify({'success': True, 'len': len(Logic.torrent_cache)})
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return jsonify({'success': False, 'log': str(e)})
    elif sub == 'tracker_update':
        try:
            Logic.update_tracker()
            return jsonify({'success': True})
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return jsonify({'success': False, 'log': str(e)})
    elif sub == 'tracker_save':
        try:
            Logic.tracker_save(request)
            return jsonify({'success': True})
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return jsonify({'success': False, 'log': str(e)})
    elif sub == 'torrent_info':
        try:
            from torrent_info import Logic as TorrentInfoLogic
            data = request.form['hash']
            logger.debug(data)
            if data.startswith('magnet'):
                ret = TorrentInfoLogic.parse_magnet_uri(data)
            else:
                ret = TorrentInfoLogic.parse_torrent_url(data)
            return jsonify(ret)
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


#########################################################
# API
#########################################################
@blueprint.route('/api/<sub>', methods=['GET', 'POST'])
def api(sub):
    logger.debug('api %s %s', package_name, sub)
    if sub == 'from_magnet':
        try:
            arg = ModelSetting.to_dict()
            # default arguments from db
            func_args = {
                'scrape': arg['scrape'] == 'True',
                'use_dht': arg['use_dht'] == 'True',
                'force_dht': arg['force_dht'] == 'True',
                'timeout': int(arg['timeout']),
                'n_try': int(arg['n_try']),
                'trackers': json.loads(arg['trackers']),
            }
            # override db_defaults by api input
            for key in request.form:
                if key in func_args:
                    func_args[key] = request.form[key]

            torrent_info = Logic.parse_magnet_uri(request.form['magnet_uri'], **func_args)
            return jsonify({'success': True, 'info': torrent_info})
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return jsonify({'sueecss': False, 'log': str(e)})
            
    elif sub == 'download_torrent':
        try:
            if request.method == 'POST':
                return jsonify({'success': False, 'log': '중지/삭제 예정 기능입니다.'})
                # info_hash = request.form.get('info_hash', '')
                # if info_hash in Logic.torrent_cache:
                #     return jsonify({
                #         'success': True, 
                #         'download_url': '/{}/api/{}?info_hash={}'.format(package_name, sub, info_hash)
                #     })
                # else:
                #     return jsonify({'success': False, 'log': '캐시에 없는 파일은 다운받을 수 없습니다.'})
            elif request.method == 'GET':
                info_hash = request.args.get('info_hash', '')
                if info_hash in Logic.torrent_cache:
                    torrent_file = base64.b64decode(Logic.torrent_cache[info_hash]['file'])
                    torrent_info = Logic.torrent_cache[info_hash]['info']
                    resp = Response(torrent_file)
                    resp.headers['Content-Type'] = 'application/x-bittorrent'
                    resp.headers['Content-Disposition'] = "attachment; filename*=UTF-8''{}".format(quote(torrent_info['name'].encode('utf-8') + '.torrent'))
                    return resp
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return jsonify({'success': False, 'log': str(e)})
            
    elif sub == 'from_file':
        try:
            fs = request.files['file']
            fs.seek(0)
            torrent_file = fs.read()
            torrent_info = Logic.parse_torrent_file(torrent_file)
            return jsonify({'success': True, 'info': torrent_info})
        except Exception as e:
            logger.error('Exception:%s', str(e))
            logger.error(traceback.format_exc())
            return jsonify({'success': False, 'log': str(e)})
            
    elif sub == 'from_url':
        try:
            res = requests.get(request.form['torrent_url'])
            res.raise_for_status()                
            torrent_info = Logic.parse_torrent_file(res.content)  
            return jsonify({'success': True, 'info': torrent_info})
        except Exception as e:
            logger.error('Exception:%s', str(e))
            logger.error(traceback.format_exc())
            return jsonify({'success': False, 'log': str(e)})
            
    elif sub == 'from_cache':
        try:
            cached = [val['info'] for key, val in Logic.torrent_cache.iteritems()]
            return jsonify({'success': True, 'info': cached})
        except Exception as e:
            logger.error('Exception:%s', str(e))
            logger.error(traceback.format_exc())
            return jsonify({'success': False, 'log': str(e)})
