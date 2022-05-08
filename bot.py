import os
import signal
import subprocess
import time

import requests
from config import load_config


class Bot:

    error = False
    running = True
    config = None
    processes = []

    logger = None

    def __init__(self, logger):
        self.logger = logger

        # load config
        self.reload_config()

        # reg signals
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

    def stop(self, signum, stack):
        if self.running:
            self.logger.info("Caught stop signal, stopping")
            self.running = False

    def reload_config(self):

        # if config not loaded at all
        if self.config is None:
            self.config = load_config()

            for idx, name in enumerate(self.config["streamers"]):
                # add info
                self.config["streamers"][idx] = [name, False]

            return

        # load new
        new_config = load_config()

        # remove all deleted streamers
        for idx, streamer in enumerate(self.config["streamers"]):
            if streamer[0] not in new_config["streamers"]:
                self.logger.info("{} has been removed".format(streamer[0]))
                del self.config["streamers"][idx]

        # add all new streamers
        for new_streamer in new_config["streamers"]:

            # find streamer
            found = False
            for streamer in self.config["streamers"]:
                if streamer[0] == new_streamer:
                    found = True

            # add if not found
            if not found:
                self.config["streamers"].append([new_streamer, False])

    def is_online(self, username):
        url = "https://cn.bongacams.com/tools/amf.php?x-country=jp"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "Connection": "close",
            "referer": "https://cn.bongacams.com/"+username
            }
        data = {"args[]": username, "method": "getRoomData"}
        # self.logger.info(headers)
        try:
            time.sleep(3)  # fix issue 30
            s = requests.session()
            # 关闭多余的连接
            s.keep_alive = False
            r = s.post(url, headers=headers, data=data)
            # if r.json()["localData"]["videoServerUrl"] == "public":
            videoServerUrl = r.json()["localData"].get('videoServerUrl','null')

            if videoServerUrl == "null":
                # self.logger.info(videoServerUrl)
                return False

            # 判断是否是公开表演，而不是私人付费表演
            if r.json()['performerData']['showType'] != "public":
                # self.logger.info(r.json()['performerData']['showType'])
                return False
            
            # 通过 m3u8 地址的有效性来判断主播在线状态
            m3u8Url = 'https:%s/hls/stream_%s/playlist.m3u8' % (videoServerUrl, username)
            # self.logger.info(m3u8Url)
            page_http_code_check_request = s.get(m3u8Url, headers=headers, proxies=proxy_ip, allow_redirects=False)
            # self.logger.info(page_http_code_check_request.status_code)
            # judgment http code 302 
            if page_http_code_check_request.status_code == 200:
                # tg 频道发送通知
                requests.get("https://api.telegram.org/bot1466882129:AAF1Ok5cF0hPh4zvE8neZseDxiPcx6GwUos/sendMessage?chat_id=570710741&text="+username)
                return True

            return False

        except Exception as e:
            self.logger.exception(e)
            return None

    def run(self):
        while self.running:
            
            # debug
            try:

                # reload config
                if self.config["auto_reload_config"]:
                    self.reload_config()

                # check current processes
                for idx, rec in enumerate(self.processes):

                    # check if ended
                    if rec[1].poll() is not None:
                        self.logger.info("Stopped recording {}".format(rec[0]))

                        # set streamer recording to false
                        for loc, streamer in enumerate(self.config["streamers"]):
                            if streamer[0] == rec[0]:
                                self.config["streamers"][loc][1] = False

                        # remove from proc list
                        del self.processes[idx]

                # check to start recording
                for idx, streamer in enumerate(self.config["streamers"]):

                    # if already recording
                    if streamer[1]:
                        continue

                    # check if online
                    if self.is_online(streamer[0]):
                        self.logger.info("Started to record {}".format(streamer[0]))

                        # prep args (dl bin and config)
                        args = self.config["youtube-dl_cmd"].split(" ") + ["https://cn.bongacams.com/{}/".format(streamer[0].lower()), "--config-location", self.config["youtube-dl_config"]] 
                        # self.logger.info(args)
                        # append idx and process to processes list
                        self.processes.append([streamer[0], subprocess.Popen(args, 0)])

                        # set to recording
                        self.config["streamers"][idx][1] = True
                    
                    # check rate limit
                    if self.config["rate_limit"]:
                        time.sleep(self.config["rate_limit_time"])

                # wait 1 min in 1 second intervals
                for i in range(60):
                    if not self.running:
                        break

                    time.sleep(1)
                
            except Exception:
                self.logger.exception("loop error")
                time.sleep(1)

        # loop ended, stop all recording
        for rec in self.processes:
            # send sigint, wait for end
            rec[1].send_signal(signal.SIGINT)
            rec[1].wait()
        
        self.logger.info("Successfully stopped")
