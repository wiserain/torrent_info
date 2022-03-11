import os
import traceback
import json
import time
from datetime import datetime
import platform
from urllib.parse import quote, urlparse

# third-party
import requests
from sqlitedict import SqliteDict
from flask import request, render_template, jsonify, Response

# pylint: disable=import-error
from framework import app, db, path_data
from framework.common.plugin import LogicModuleBase
from system.logic_command2 import SystemLogicCommand2 as SystemCommand

# pylint: disable=relative-beyond-top-level
from .plugin import plugin
from .util import pathscrub, size_fmt

logger = plugin.logger
package_name = plugin.package_name
plugin_info = plugin.plugin_info
ModelSetting = plugin.ModelSetting


class LogicMain(LogicModuleBase):
    db_default = {
        "use_dht": "True",
        "scrape": "False",
        "timeout": "15",
        "trackers": "",
        "n_try": "3",
        "tracker_last_update": "1970-01-01",
        "tracker_update_every": "30",
        "tracker_update_from": "best",
        "libtorrent_build": "191217",
        "http_proxy": "",
        "list_pagesize": "20",
    }

    torrent_cache = None

    tracker_update_from_list = ["best", "all", "all_udp", "all_http", "all_https", "all_ws", "best_ip", "all_ip"]

    def __init__(self, P):
        super().__init__(P, None)

    def plugin_load(self):
        try:
            # 토렌트 캐쉬 초기화
            self.cache_init()

            # libtorrent 자동 설치
            new_build = int(plugin_info["install"].rsplit("-", maxsplit=1)[-1])
            installed_build = ModelSetting.get_int("libtorrent_build")
            if (new_build > installed_build) or (not self.is_installed()):
                self.install(show_modal=False)

            # tracker 자동 업데이트
            tracker_update_every = ModelSetting.get_int("tracker_update_every")
            tracker_last_update = ModelSetting.get("tracker_last_update")
            if tracker_update_every > 0:
                if (datetime.now() - datetime.strptime(tracker_last_update, "%Y-%m-%d")).days >= tracker_update_every:
                    self.update_tracker()
        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())

    def process_menu(self, sub, req):
        arg = ModelSetting.to_dict()
        arg["package_name"] = package_name
        if sub == "setting":
            arg["trackers"] = "\n".join(json.loads(arg["trackers"]))
            arg["tracker_update_from_list"] = [
                [x, f"https://ngosang.github.io/trackerslist/trackers_{x}.txt"] for x in self.tracker_update_from_list
            ]
            arg["plugin_ver"] = plugin_info["version"]
            from system.model import ModelSetting as SystemModelSetting

            ddns = SystemModelSetting.get("ddns")
            arg["json_api"] = f"{ddns}/{package_name}/api/json"
            arg["m2t_api"] = f"{ddns}/{package_name}/api/m2t"
            if SystemModelSetting.get_bool("auth_use_apikey"):
                arg["json_api"] += f"?apikey={SystemModelSetting.get('auth_apikey')}"
                arg["m2t_api"] += f"?apikey={SystemModelSetting.get('auth_apikey')}"
            return render_template(f"{package_name}_{sub}.html", sub=sub, arg=arg)
        if sub == "search":
            arg["cache_size"] = len(self.torrent_cache)
            return render_template(f"{package_name}_{sub}.html", arg=arg)
        return render_template("sample.html", title=f"{package_name} - {sub}")

    def process_ajax(self, sub, req):
        if sub == "install":
            return jsonify(self.install())
        if sub == "is_installed":
            try:
                is_installed = self.is_installed()
                if is_installed:
                    ret = {"installed": True, "version": is_installed}
                else:
                    ret = {"installed": False}
                return jsonify(ret)
            except Exception as e:
                logger.error("Exception:%s", e)
                logger.error(traceback.format_exc())
        if sub == "uninstall":
            return jsonify(self.uninstall())
        if sub == "cache":
            try:
                p = request.form.to_dict() if request.method == "POST" else request.args.to_dict()
                action = p.get("action", "")
                infohash = p.get("infohash", "")
                name = p.get("name", "")
                if action == "clear":
                    self.torrent_cache.clear()
                elif action == "delete" and infohash:
                    for h in infohash.split(","):
                        if h and h in self.torrent_cache:
                            del self.torrent_cache[h]
                # filtering
                if name:
                    info = (val["info"] for val in self.torrent_cache.values() if name.strip() in val["info"]["name"])
                elif infohash:
                    info = (self.torrent_cache[h]["info"] for h in infohash.split(",") if h and h in self.torrent_cache)
                else:
                    info = (val["info"] for val in self.torrent_cache.values())
                info = sorted(info, key=lambda x: x["creation_date"], reverse=True)
                total = len(info)
                if p.get("c", ""):
                    counter = int(p.get("c"))
                    pagesize = ModelSetting.get_int("list_pagesize")
                    if counter == 0:
                        info = info[:pagesize]
                    elif counter == len(info):
                        info = []
                    else:
                        info = info[counter : counter + pagesize]
                # return
                if action == "list":
                    return jsonify({"success": True, "info": info, "total": total})
                return jsonify({"success": True, "count": len(info)})
            except Exception as e:
                logger.error("Exception:%s", e)
                logger.error(traceback.format_exc())
                return jsonify({"success": False, "log": str(e)})
        if sub == "tracker_update":
            try:
                self.update_tracker()
                return jsonify({"success": True})
            except Exception as e:
                logger.error("Exception:%s", e)
                logger.error(traceback.format_exc())
                return jsonify({"success": False, "log": str(e)})
        if sub == "tracker_save":
            try:
                self.tracker_save(request)
                return jsonify({"success": True})
            except Exception as e:
                logger.error("Exception:%s", e)
                logger.error(traceback.format_exc())
                return jsonify({"success": False, "log": str(e)})
        if sub == "torrent_info":
            # for global use - default arguments by function itself
            try:
                from torrent_info import Logic as TorrentInfoLogic

                data = request.form["hash"]
                logger.debug(data)
                if data.startswith("magnet"):
                    ret = TorrentInfoLogic.parse_magnet_uri(data)
                else:
                    ret = TorrentInfoLogic.parse_torrent_url(data)
                return jsonify(ret)
            except Exception as e:
                logger.error("Exception:%s", e)
                logger.error(traceback.format_exc())
        if sub == "get_torrent_info":
            # for local use - default arguments from user db
            try:
                if request.form["uri_url"].startswith("magnet"):
                    torrent_info = self.parse_magnet_uri(request.form["uri_url"])
                else:
                    torrent_info = self.parse_torrent_url(request.form["uri_url"])
                return jsonify({"success": True, "info": torrent_info})
            except Exception as e:
                logger.error("Exception:%s", e)
                logger.error(traceback.format_exc())
                return jsonify({"success": False, "log": str(e)})
        if sub == "get_file_info":
            try:
                fs = request.files["file"]
                fs.seek(0)
                torrent_file = fs.read()
                torrent_info = self.parse_torrent_file(torrent_file)
                return jsonify({"success": True, "info": torrent_info})
            except Exception as e:
                logger.error("Exception:%s", str(e))
                logger.error(traceback.format_exc())
                return jsonify({"success": False, "log": str(e)})
        if sub == "get_torrent_file" and request.method == "GET":
            try:
                data = request.args.to_dict()
                magnet_uri = data.get("uri", "")
                if not magnet_uri.startswith("magnet"):
                    magnet_uri = "magnet:?xt=urn:btih:" + magnet_uri
                torrent_file, torrent_name = self.parse_magnet_uri(magnet_uri, no_cache=True, to_torrent=True)
                resp = Response(torrent_file)
                resp.headers["Content-Type"] = "application/x-bittorrent"
                resp.headers["Content-Disposition"] = "attachment; filename*=UTF-8''" + quote(torrent_name + ".torrent")
                return resp
            except Exception as e:
                return jsonify({"success": False, "log": str(e)})

    def process_api(self, sub, req):
        try:
            if sub == "json":
                data = request.form.to_dict() if request.method == "POST" else request.args.to_dict()
                if data.get("uri", ""):
                    magnet_uri = data.get("uri")
                    if not magnet_uri.startswith("magnet"):
                        magnet_uri = "magnet:?xt=urn:btih:" + magnet_uri

                    # override db default by api input
                    func_args = {}
                    for k in ["scrape", "use_dht", "no_cache"]:
                        if k in data:
                            func_args[k] = data.get(k).lower() == "true"
                    for k in ["timeout", "n_try"]:
                        if k in data:
                            func_args[k] = int(data.get(k))

                    torrent_info = self.parse_magnet_uri(magnet_uri, **func_args)
                elif data.get("url", ""):
                    torrent_info = self.parse_torrent_url(data.get("url"))
                else:
                    return jsonify({"success": False, "log": 'At least one of "uri" or "url" parameter required'})
                return jsonify({"success": True, "info": torrent_info})

            if sub == "m2t":
                if request.method == "POST":
                    return jsonify({"success": False, "log": "POST method not allowed"})
                data = request.args.to_dict()
                magnet_uri = data.get("uri", "")
                if not magnet_uri.startswith("magnet"):
                    magnet_uri = "magnet:?xt=urn:btih:" + magnet_uri

                # override db default by api input
                func_args = {}
                for k in ["scrape", "use_dht"]:
                    if k in data:
                        func_args[k] = data.get(k).lower() == "true"
                for k in ["timeout", "n_try"]:
                    if k in data:
                        func_args[k] = int(data.get(k))
                func_args.update({"no_cache": True, "to_torrent": True})
                torrent_file, torrent_name = self.parse_magnet_uri(magnet_uri, **func_args)
                resp = Response(torrent_file)
                resp.headers["Content-Type"] = "application/x-bittorrent"
                resp.headers["Content-Disposition"] = "attachment; filename*=UTF-8''" + quote(torrent_name + ".torrent")
                return resp
        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())
            return jsonify({"success": False, "log": str(e)})

    def cache_init(self):
        if self.torrent_cache is None:
            db_file = os.path.join(path_data, "db", f"{package_name}.db")
            self.torrent_cache = SqliteDict(
                db_file, tablename=f"plugin_{package_name}_cache", encode=json.dumps, decode=json.loads, autocommit=True
            )

    def tracker_save(self, req):
        for key, value in req.form.items():
            logger.debug({"key": key, "value": value})
            if key == "trackers":
                value = json.dumps(value.split("\n"))
            logger.debug("Key:%s Value:%s", key, value)
            entity = db.session.query(ModelSetting).filter_by(key=key).with_for_update().first()
            entity.value = value
        db.session.commit()

    def update_tracker(self):
        # https://github.com/ngosang/trackerslist
        src_url = f"https://ngosang.github.io/trackerslist/trackers_{ModelSetting.get('tracker_update_from')}.txt"
        new_trackers = requests.get(src_url).content.decode("utf8").split("\n\n")[:-1]
        ModelSetting.set("trackers", json.dumps(new_trackers))
        ModelSetting.set("tracker_last_update", datetime.now().strftime("%Y-%m-%d"))

    def is_installed(self):
        try:
            import libtorrent as lt

            return lt.version
        except ImportError:
            return False

    def install(self, show_modal=True):
        try:
            # platform check - whitelist
            if platform.system() == "Linux" and app.config["config"]["running_type"] == "docker":
                install_sh = os.path.join(os.path.dirname(__file__), "install.sh")
                commands = [
                    ["msg", "잠시만 기다려주세요."],
                    ["chmod", "+x", install_sh],
                    [install_sh, "-delete"],
                    [install_sh, plugin_info["install"]],
                    ["msg", "완료되었습니다."],
                ]
                SystemCommand("libtorrent 설치", commands, wait=True, show_modal=show_modal, clear=True).start()
                return {"success": True}
            return {"succes": False, "log": "지원하지 않는 시스템입니다."}
        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())
            return {"success": False, "log": str(e)}

    def uninstall(self):
        try:
            if platform.system() == "Linux" and app.config["config"]["running_type"] == "docker":
                install_sh = os.path.join(os.path.dirname(__file__), "install.sh")
                commands = [
                    ["msg", "잠시만 기다려주세요."],
                    ["chmod", "+x", install_sh],
                    [install_sh, "-delete"],
                    ["msg", "완료되었습니다."],
                ]
                SystemCommand("libtorrent 삭제", commands, wait=True, show_modal=True, clear=True).start()
                return {"success": True}
            return {"succes": False, "log": "지원하지 않는 시스템입니다."}
        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())
            return {"success": False, "log": str(e)}

    def convert_torrent_info(self, torrent_info):
        """from libtorrent torrent_info to python dictionary object"""
        try:
            import libtorrent as lt
        except ImportError as _e:
            raise ImportError("libtorrent package required") from _e

        return {
            "name": torrent_info.name(),
            "num_files": torrent_info.num_files(),
            "total_size": torrent_info.total_size(),  # in byte
            "total_size_fmt": size_fmt(torrent_info.total_size()),  # in byte
            "info_hash": str(torrent_info.info_hash()),  # original type: libtorrent.sha1_hash
            "num_pieces": torrent_info.num_pieces(),
            "creator": torrent_info.creator() if torrent_info.creator() else f"libtorrent v{lt.version}",
            "comment": torrent_info.comment(),
            "files": [
                {"path": file.path, "size": file.size, "size_fmt": size_fmt(file.size)} for file in torrent_info.files()
            ],
            "magnet_uri": lt.make_magnet_uri(torrent_info),
        }

    def parse_magnet_uri(
        self,
        magnet_uri,
        scrape=None,
        use_dht=None,
        timeout=None,
        trackers=None,
        no_cache=None,
        n_try=None,
        to_torrent=None,
        http_proxy=None,
    ):
        try:
            import libtorrent as lt
        except ImportError as _e:
            raise ImportError("libtorrent package required") from _e

        # default function arguments from db
        if scrape is None:
            scrape = ModelSetting.get_bool("scrape")
        if use_dht is None:
            use_dht = ModelSetting.get_bool("use_dht")
        if timeout is None:
            timeout = ModelSetting.get_int("timeout")
        if trackers is None:
            trackers = json.loads(ModelSetting.get("trackers"))
        if n_try is None:
            n_try = ModelSetting.get_int("n_try")
        if no_cache is None:
            no_cache = False
        if to_torrent is None:
            to_torrent = False
        if http_proxy is None:
            http_proxy = ModelSetting.get("http_proxy")

        # parameters
        params = lt.parse_magnet_uri(magnet_uri)

        # prevent downloading
        # https://stackoverflow.com/q/45680113
        if isinstance(params, dict):
            params["flags"] |= lt.add_torrent_params_flags_t.flag_upload_mode
        else:
            params.flags |= lt.add_torrent_params_flags_t.flag_upload_mode

        lt_version = [int(v) for v in lt.version.split(".")]
        if [0, 16, 13, 0] < lt_version < [1, 1, 3, 0]:
            # for some reason the info_hash needs to be bytes but it's a struct called sha1_hash
            if isinstance(params, dict):
                params["info_hash"] = params["info_hash"].to_bytes()
            else:
                params.info_hash = params.info_hash.to_bytes()

        # 캐시에 있으면...
        info_hash_from_magnet = str(params["info_hash"] if isinstance(params, dict) else params.info_hash)
        self.cache_init()
        if (not no_cache) and (info_hash_from_magnet in self.torrent_cache):
            return self.torrent_cache[info_hash_from_magnet]["info"]

        # add trackers
        if isinstance(params, dict):
            if len(params["trackers"]) == 0:
                params["trackers"] = trackers
        else:
            if len(params.trackers) == 0:
                params.trackers = trackers

        # session
        settings = {
            # basics
            # 'user_agent': 'libtorrent/' + lt.__version__,
            "listen_interfaces": "0.0.0.0:6881",
            # dht
            "enable_dht": use_dht,
            "use_dht_as_fallback": True,
            "dht_bootstrap_nodes": "router.bittorrent.com:6881,dht.transmissionbt.com:6881,router.utorrent.com:6881,127.0.0.1:6881",
            "enable_lsd": False,
            "enable_upnp": True,
            "enable_natpmp": True,
            "announce_to_all_tiers": True,
            "announce_to_all_trackers": True,
            "aio_threads": 4 * 2,
            "checking_mem_usage": 1024 * 2,
        }
        if http_proxy:
            proxy_url = urlparse(http_proxy)
            settings.update(
                {
                    "proxy_username": proxy_url.username,
                    "proxy_password": proxy_url.password,
                    "proxy_hostname": proxy_url.hostname,
                    "proxy_port": proxy_url.port,
                    "proxy_type": lt.proxy_type_t.http_pw
                    if proxy_url.username and proxy_url.password
                    else lt.proxy_type_t.http,
                    "force_proxy": True,
                    "anonymous_mode": True,
                }
            )
        session = lt.session(settings)

        session.add_extension("ut_metadata")
        session.add_extension("ut_pex")
        session.add_extension("metadata_transfer")

        # handle
        handle = session.add_torrent(params)

        if use_dht:
            handle.force_dht_announce()

        max_try = max(n_try, 1)
        for tryid in range(max_try):
            timeout_value = timeout
            logger.debug("Trying to get metadata... %d/%d", tryid + 1, max_try)
            while not handle.has_metadata():
                time.sleep(0.1)
                timeout_value -= 0.1
                if timeout_value <= 0:
                    break

            if handle.has_metadata():
                lt_info = handle.get_torrent_info()
                logger.debug(
                    "Successfully got metadata after %d*%d+%.2f seconds", tryid, timeout, timeout - timeout_value
                )
                time_metadata = tryid * timeout + (timeout - timeout_value)
                break
            if tryid + 1 == max_try:
                session.remove_torrent(handle, True)
                raise Exception(f"Timed out after {max_try}*{timeout} seconds")

        # create torrent object and generate file stream
        torrent = lt.create_torrent(lt_info)
        torrent.set_creator(f"libtorrent v{lt.version}")  # signature
        torrent_dict = torrent.generate()

        torrent_info = self.convert_torrent_info(lt_info)
        torrent_info.update(
            {
                "trackers": params.trackers if not isinstance(params, dict) else params["trackers"],
                "creation_date": datetime.fromtimestamp(torrent_dict[b"creation date"]).isoformat(),
                "time": {"total": time_metadata, "metadata": time_metadata},
            }
        )

        if scrape:
            # start scraping
            for tryid in range(max_try):
                timeout_value = timeout
                logger.debug("Trying to get peerinfo... %d/%d", tryid + 1, max_try)
                while handle.status(0).num_complete < 0:
                    time.sleep(0.1)
                    timeout_value -= 0.1
                    if timeout_value <= 0:
                        break

                if handle.status(0).num_complete >= 0:
                    torrent_status = handle.status(0)
                    logger.debug(
                        "Successfully got peerinfo after %d*%d+%.2f seconds", tryid, timeout, timeout - timeout_value
                    )
                    time_scrape = tryid * timeout + (timeout - timeout_value)

                    torrent_info.update(
                        {
                            "seeders": torrent_status.num_complete,
                            "peers": torrent_status.num_incomplete,
                        }
                    )
                    torrent_info["time"]["scrape"] = time_scrape
                    torrent_info["time"]["total"] = torrent_info["time"]["metadata"] + torrent_info["time"]["scrape"]
                    break
                if tryid + 1 == max_try:
                    logger.error("Timed out after %d*%d seconds", max_try, timeout)

        session.remove_torrent(handle, True)

        # caching for later use
        self.torrent_cache[torrent_info["info_hash"]] = {
            "info": torrent_info,
        }
        if to_torrent:
            return lt.bencode(torrent_dict), pathscrub(lt_info.name(), os="windows", filename=True)
        return torrent_info

    def parse_torrent_file(self, torrent_file):
        # torrent_file >> torrent_dict >> lt_info >> torrent_info
        try:
            import libtorrent as lt
        except ImportError as _e:
            raise ImportError("libtorrent package required") from _e

        torrent_dict = lt.bdecode(torrent_file)
        lt_info = lt.torrent_info(torrent_dict)
        torrent_info = self.convert_torrent_info(lt_info)
        if b"announce-list" in torrent_dict:
            torrent_info.update({"trackers": [x.decode("utf-8") for x in torrent_dict[b"announce-list"][0]]})
        creation_date = torrent_dict[b"creation date"] if b"creation date" in torrent_dict else 0
        torrent_info.update({"creation_date": datetime.fromtimestamp(creation_date).isoformat()})

        # caching for later use
        self.cache_init()
        self.torrent_cache[torrent_info["info_hash"]] = {
            "info": torrent_info,
        }
        return torrent_info

    def parse_torrent_url(self, url, http_proxy=None):
        if http_proxy is None:
            http_proxy = ModelSetting.get("http_proxy")
        if http_proxy:
            return self.parse_torrent_file(requests.get(url, proxies={"http": http_proxy, "https": http_proxy}).content)
        return self.parse_torrent_file(requests.get(url).content)
