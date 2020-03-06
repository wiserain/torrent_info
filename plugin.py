# -*- coding: utf-8 -*-
#########################################################
# 고정영역
#########################################################
# python
import os
import traceback
import json
from urllib import quote

# third-party
from flask import Blueprint, request, render_template, redirect, jsonify, Response
from flask_login import login_required

# sjva 공용
from framework.logger import get_logger
from framework import app, db, scheduler, check_api

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
    "version": "0.0.1.7",
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
    if sub == 'setting':
        arg = ModelSetting.to_dict()
        arg['trackers'] = '\n'.join(json.loads(arg['trackers']))
        arg['plugin_ver'] = plugin_info['version']
        from system.model import ModelSetting as SystemModelSetting
        ddns = SystemModelSetting.get('ddns')
        arg['api_url_base'] = '%s/%s/api' % (ddns, package_name)
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
@login_required
def ajax(sub):
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
            info = [val['info'] for _, val in Logic.torrent_cache.iteritems()]
            return jsonify({'success': True, 'info': info})
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
        # for global use - default arguments by function itself
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
    elif sub == 'get_torrent_info':
        # for local use - default arguments from user db
        try:
            if request.form['uri_url'].startswith('magnet'):
                arg = ModelSetting.to_dict()
                func_args = {
                    'scrape': arg['scrape'] == 'True',
                    'use_dht': arg['use_dht'] == 'True',
                    'force_dht': arg['force_dht'] == 'True',
                    'timeout': int(arg['timeout']),
                    'n_try': int(arg['n_try']),
                }
                torrent_info = Logic.parse_magnet_uri(request.form['uri_url'], **func_args)
            else:
                torrent_info = Logic.parse_torrent_url(request.form['uri_url'])
            return jsonify({'success': True, 'info': torrent_info})
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return jsonify({'sueecss': False, 'log': str(e)})
    elif sub == 'get_file_info':
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


#########################################################
# API
#########################################################
@blueprint.route('/api/<sub>', methods=['GET', 'POST'])
@check_api
def api(sub):
    try:
        if sub == 'json':
            if request.form.get('uri', ''):
                magnet_uri = request.form.get('uri')
                if not magnet_uri.startswith('magnet'):
                    magnet_uri = 'magnet:?xt=urn:btih:' + magnet_uri

                arg = ModelSetting.to_dict()
                # default arguments from db
                func_args = {
                    'scrape': arg['scrape'] == 'True',
                    'use_dht': arg['use_dht'] == 'True',
                    'timeout': int(arg['timeout']),
                    'n_try': int(arg['n_try']),
                }
                torrent_info = Logic.parse_magnet_uri(magnet_uri, **func_args)
            elif request.form.get('url', ''):
                torrent_info = Logic.parse_torrent_url(request.form.get('url'))
            else:
                return jsonify({'success': False, 'log': '"uri" or "url" parameter required'})
            return jsonify({'success': True, 'info': torrent_info})
        elif sub == 'from_magnet':
            # will be DEPRECATED!!!
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
