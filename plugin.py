# -*- coding: utf-8 -*-
#########################################################
# 고정영역
#########################################################
# python
import os
import sys
import traceback
import json
from urllib import quote
import requests

# third-party
from flask import Blueprint, request, render_template, redirect, jsonify, Response
from flask_login import login_required

# sjva 공용
from framework.logger import get_logger
from framework import app, db, scheduler
from framework.util import Util
            
# 패키지
from logic import Logic
from model import ModelSetting
package_name = __name__.split('.')[0].split('_sjva')[0]
logger = get_logger(package_name)

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
    "version": "0.0.0.1",
    "name": "torrent_info",
    "home": "https://github.com/wiserain/torrent_info_sjva",
    "more": "https://github.com/wiserain/torrent_info_sjva",
    "description": "토렌트 마그넷/파일 정보를 보여주는 플러그인",
    "developer": "wiserain",
    "zip": "https://github.com/wiserain/torrent_info_sjva/archive/master.zip",
    "icon": "",
    "libtorrent_tarball": "libtorrent-1.2.3-191217.tar.gz",
}
#########################################################


# 메뉴 구성.
menu = {
    'main': [package_name, '토렌트 정보'],
    'sub': [
        ['setting', '설정'], ['magnet', '마그넷'], ['torrent', '토렌트'], ['log', '로그']
    ],
    'category': 'torrent',
}


#########################################################
# WEB Menu
#########################################################
@blueprint.route('/')
def home():
    return redirect('/%s/magnet' % package_name)


@blueprint.route('/<sub>')
@login_required
def detail(sub):
    logger.debug('menu %s %s', package_name, sub)
    if sub == 'setting':
        setting_list = db.session.query(ModelSetting).all()
        arg = Util.db_list_to_dict(setting_list)
        arg['scheduler'] = str(scheduler.is_include(package_name))
        arg['is_running'] = str(scheduler.is_running(package_name))
        return render_template('%s_setting.html' % package_name, sub=sub, arg=arg)
    elif sub == 'magnet':
        setting_list = db.session.query(ModelSetting).all()
        arg = Util.db_list_to_dict(setting_list)
        return render_template('%s_magnet.html' % package_name, arg=arg)
    elif sub == 'torrent':
        setting_list = db.session.query(ModelSetting).all()
        arg = Util.db_list_to_dict(setting_list)
        return render_template('%s_torrent.html' % package_name, arg=arg)
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
    # 스케쥴링 on / off
    elif sub == 'scheduler':
        try:
            go = request.form['scheduler']
            logger.debug('scheduler:%s', go)
            if go == 'true':
                Logic.scheduler_start()
            else:
                Logic.scheduler_stop()
            return jsonify(go)
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return jsonify('fail')
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

#########################################################
# API
#########################################################
@blueprint.route('/api/<sub>', methods=['GET', 'POST'])
def api(sub):
    logger.debug('api %s %s', package_name, sub)
    if sub == 'magnet_info':
        try:
            setting_list = db.session.query(ModelSetting).all()
            arg = Util.db_list_to_dict(setting_list)
            # default arguments from db
            func_args = {
                'scrape': arg['scrape'] == 'True',
                'use_dht': arg['use_dht'] == 'True',
                'force_dht': arg['force_dht'] == 'True',
                'timeout': int(arg['timeout']),
                'trackers': json.loads(arg['trackers']),
            }
            # override db_defaults by api input
            for key in request.form:
                if key in func_args:
                    func_args[key] = request.form

            magnet_info = Logic.parse_magnet_uri(request.form['magnet_uri'], **func_args)
            return jsonify({'success': True, 'info': magnet_info})
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return jsonify({'sueecss': False, 'log': str(e)})
            
    elif sub == 'download_torrent':
        try:
            hash = request.args.get('hash')
            if hash in Logic.cached_torrent:
                torrent_file = Logic.cached_torrent[hash]['file']
                torrent_name = Logic.cached_torrent[hash]['name']
                resp = Response(torrent_file)
                resp.headers['Content-Type'] = 'application/x-bittorrent'
                resp.headers['Content-Disposition'] = "attachment; filename*=UTF-8''{}".format(quote(torrent_name + '.torrent'))
                return resp
            else:
                logger.warning('hash expired: %s', hash)
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            
    elif sub == 'torrent_info_file':
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
            
    elif sub == 'torrent_info_url':
        try:
            res = requests.get(request.form['torrent_url'])
            torrent_info = Logic.parse_torrent_file(res.content)
            return jsonify({'success': True, 'info': torrent_info})
        except Exception as e:
            logger.error('Exception:%s', str(e))
            logger.error(traceback.format_exc())
            return jsonify({'success': False, 'log': str(e)})
        