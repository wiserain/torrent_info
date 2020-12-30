# -*- coding: utf-8 -*-
#########################################################
# 고정영역
#########################################################
# python
import os
import traceback
import json
try:
    from urllib import quote  # Python 2.X
except ImportError:
    from urllib.parse import quote  # Python 3+

# third-party
from flask import Blueprint, request, render_template, redirect, jsonify, Response
from flask_login import login_required

# sjva 공용
from framework.logger import get_logger
from framework import app, db, scheduler, check_api

# 패키지
package_name = __name__.split('.')[0]
logger = get_logger(package_name)

from .logic import Logic
from .model import ModelSetting

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
    "version": "0.0.9.2",
    "name": "torrent_info",
    "home": "https://github.com/wiserain/torrent_info",
    "more": "https://github.com/wiserain/torrent_info",
    "description": "토렌트 마그넷/파일 정보를 보여주는 플러그인",
    "developer": "wiserain",
    "zip": "https://github.com/wiserain/torrent_info/archive/master.zip",
    "icon": "",
    "install": "2.0.1-201230",
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
        arg['package_name'] = package_name
        arg['trackers'] = '\n'.join(json.loads(arg['trackers']))
        arg['tracker_update_from_list'] = [[x, 'https://ngosang.github.io/trackerslist/trackers_%s.txt' % x] for x in Logic.tracker_update_from_list]
        arg['plugin_ver'] = plugin_info['version']
        from system.model import ModelSetting as SystemModelSetting
        ddns = SystemModelSetting.get('ddns')
        arg['json_api'] = '%s/%s/api/json' % (ddns, package_name)
        arg['m2t_api'] = '%s/%s/api/m2t' % (ddns, package_name)
        if SystemModelSetting.get_bool('auth_use_apikey'):
            arg['json_api'] += '?apikey=%s' % SystemModelSetting.get('auth_apikey')
            arg['m2t_api'] += '?apikey=%s' % SystemModelSetting.get('auth_apikey')
        return render_template('%s_setting.html' % package_name, sub=sub, arg=arg)
    elif sub == 'search':
        arg = ModelSetting.to_dict()
        arg['package_name'] = package_name
        arg['cache_size'] = len(Logic.torrent_cache)
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
    elif sub == 'uninstall':
        try:
            ret = Logic.uninstall()
            return jsonify(ret)
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
    elif sub == 'cache':
        try:
            p = request.form.to_dict() if request.method == 'POST' else request.args.to_dict()
            action = p.get('action', '')
            infohash = p.get('infohash', '')
            name = p.get('name', '')
            if action == 'clear':
                Logic.torrent_cache.clear()
            elif action == 'delete' and infohash:
                for h in infohash.split(','):
                    if h and h in Logic.torrent_cache:
                        del Logic.torrent_cache[h]
            # filtering
            if name:
                info = [val['info'] for _, val in Logic.torrent_cache.iteritems() if name.strip() in val['info']['name']]
            elif infohash:
                info = [Logic.torrent_cache[h]['info'] for h in infohash.split(',') if h and h in Logic.torrent_cache]
            else:
                info = [val['info'] for _, val in Logic.torrent_cache.iteritems()]
            info = sorted(info, key=lambda x: x['creation_date'], reverse=True)
            total = len(info)
            if p.get('c', ''):
                counter = int(p.get('c'))
                pagesize = ModelSetting.get_int('list_pagesize')
                if counter == 0:
                    info = info[:pagesize]
                elif counter == len(info):
                    info = []
                else:
                    info = info[counter:counter+pagesize]
            # return
            if action == 'list':
                return jsonify({'success': True, 'info': info, 'total': total})
            else:
                return jsonify({'success': True, 'count': len(info)})
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
                torrent_info = Logic.parse_magnet_uri(request.form['uri_url'])
            else:
                torrent_info = Logic.parse_torrent_url(request.form['uri_url'])
            return jsonify({'success': True, 'info': torrent_info})
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return jsonify({'success': False, 'log': str(e)})
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
    elif sub == 'get_torrent_file' and request.method == 'GET':
        try:
            data = request.args.to_dict()
            magnet_uri = data.get('uri', '')
            if not magnet_uri.startswith('magnet'):
                magnet_uri = 'magnet:?xt=urn:btih:' + magnet_uri
            torrent_file, torrent_name = Logic.parse_magnet_uri(magnet_uri, no_cache=True, to_torrent=True)
            resp = Response(torrent_file)
            resp.headers['Content-Type'] = 'application/x-bittorrent'
            resp.headers['Content-Disposition'] = "attachment; filename*=UTF-8''{}".format(quote(torrent_name + '.torrent'))
            return resp
        except Exception as e:
            return jsonify({'success': False, 'log': str(e)})


#########################################################
# API
#########################################################
@blueprint.route('/api/<sub>', methods=['GET', 'POST'])
@check_api
def api(sub):
    try:
        if sub == 'json':
            data = request.form.to_dict() if request.method == 'POST' else request.args.to_dict()
            if data.get('uri', ''):
                magnet_uri = data.get('uri')
                if not magnet_uri.startswith('magnet'):
                    magnet_uri = 'magnet:?xt=urn:btih:' + magnet_uri

                # override db default by api input
                func_args = {}
                for k in ['scrape', 'use_dht', 'no_cache']:
                    if k in data:
                        func_args[k] = data.get(k).lower() == 'true'
                for k in ['timeout', 'n_try']:
                    if k in data:
                        func_args[k] = int(data.get(k))

                torrent_info = Logic.parse_magnet_uri(magnet_uri, **func_args)
            elif data.get('url', ''):
                torrent_info = Logic.parse_torrent_url(data.get('url'))
            else:
                return jsonify({'success': False, 'log': 'At least one of "uri" or "url" parameter required'})
            return jsonify({'success': True, 'info': torrent_info})

        elif sub == 'm2t':
            if request.method == 'POST':
                return jsonify({'success': False, 'log': 'POST method not allowed'})
            data = request.args.to_dict()
            magnet_uri = data.get('uri', '')
            if not magnet_uri.startswith('magnet'):
                magnet_uri = 'magnet:?xt=urn:btih:' + magnet_uri

            # override db default by api input
            func_args = {}
            for k in ['scrape', 'use_dht']:
                if k in data:
                    func_args[k] = data.get(k).lower() == 'true'
            for k in ['timeout', 'n_try']:
                if k in data:
                    func_args[k] = int(data.get(k))
            func_args.update({'no_cache': True, 'to_torrent': True})
            torrent_file, torrent_name = Logic.parse_magnet_uri(magnet_uri, **func_args)
            resp = Response(torrent_file)
            resp.headers['Content-Type'] = 'application/x-bittorrent'
            resp.headers['Content-Disposition'] = "attachment; filename*=UTF-8''{}".format(quote(torrent_name + '.torrent'))
            return resp
    except Exception as e:
        logger.error('Exception:%s', e)
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'log': str(e)})
