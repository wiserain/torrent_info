import os

# third-party
from flask import Blueprint

# pylint: disable=import-error
from framework.logger import get_logger
from framework.common.plugin import get_model_setting, Logic, default_route_single_module


class PlugIn:
    package_name = __name__.split(".", maxsplit=1)[0]
    logger = get_logger(package_name)
    ModelSetting = get_model_setting(package_name, logger, table_name=f"plugin_{package_name}_setting")

    blueprint = Blueprint(
        package_name,
        package_name,
        url_prefix=f"/{package_name}",
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
    )

    plugin_info = {
        "category_name": "torrent",
        "version": "0.1.4",
        "name": "torrent_info",
        "home": "https://github.com/wiserain/torrent_info",
        "more": "https://github.com/wiserain/torrent_info",
        "description": "토렌트 마그넷/파일 정보를 보여주는 플러그인",
        "developer": "wiserain",
        "zip": "https://github.com/wiserain/torrent_info/archive/master.zip",
        "icon": "",
        "install": "2.0.5-220308",
    }

    menu = {
        "main": [package_name, "토렌트 정보"],
        "sub": [["setting", "설정"], ["search", "검색"], ["log", "로그"]],
        "category": "torrent",
    }
    home_module = "search"

    module_list = None
    logic = None

    def __init__(self):
        from framework import app, path_data

        db_file = os.path.join(path_data, "db", f"{self.package_name}.db")
        app.config["SQLALCHEMY_BINDS"][self.package_name] = f"sqlite:///{db_file}"

        from framework.util import Util

        Util.save_from_dict_to_json(self.plugin_info, os.path.join(os.path.dirname(__file__), "info.json"))


plugin = PlugIn()

# pylint: disable=relative-beyond-top-level
from .logic import LogicMain

plugin.module_list = [LogicMain(plugin)]

# (logger, package_name, module_list, ModelSetting) required for Logic
plugin.logic = Logic(plugin)
# (;ogger, package_name, module_list, ModelSetting, blueprint, logic) required for default_route
default_route_single_module(plugin)
