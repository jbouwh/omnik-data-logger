import json
from datetime import datetime
import pytz
from ha_logger import hybridlogger

import urllib.parse
import requests
from omnik.plugins import Plugin


class pvoutput(Plugin):

    def __init__(self):
        super().__init__()
        self.name = 'pvoutput'
        self.description = 'Write output to PVOutput'
        tz = self.config.get('default', 'timezone',
                             fallback='Europe/Amsterdam')
        self.timezone = pytz.timezone(tz)

    def get_weather(self, hass_api):
        try:
            if 'weather' not in self.cache:
                self.logger.debug('[cache miss] Fetching weather data')
                url = "https://{endpoint}/data/2.5/weather?lon={lon}&lat={lat}&units={units}&APPID={api_key}".format(
                    endpoint=self.config.get('openweathermap', 'endpoint', fallback='api.openweathermap.org'),
                    lat=self.config.get('openweathermap', 'lat'),
                    lon=self.config.get('openweathermap', 'lon'),
                    units=self.config.get(
                        'openweathermap', 'units', fallback='metric'),
                    api_key=self.config.get('openweathermap', 'api_key'),
                )

                res = requests.get(url)

                res.raise_for_status()

                self.cache['weather'] = res.json()

            return self.cache['weather']

        except requests.exceptions.HTTPError as e:
            hybridlogger.ha_log(self.logger, self.hass_api, "ERROR",'Unable to get data. [{0}]: {1}'.format(
                type(e).__name__, str(e)))
            raise e

    def process(self, **args):
        """
        Send data to pvoutput
        """
        try:

            msg = args['msg']
            reporttime=datetime.strptime(f"{msg['last_update_time']} UTC+0000", '%Y-%m-%dT%H:%M:%SZ %Z%z').astimezone(self.timezone)
            #now = self.timezone.normalize(self.timezone.fromutc(datetime.utcnow()))

            self.logger.debug(json.dumps(msg, indent=2))

            if not self.config.has_option('pvoutput', 'sys_id') or not self.config.has_option('pvoutput', 'api_key'):
                hybridlogger.ha_log(self.logger, self.hass_api, "ERROR",
                    f'[{__name__}] No api_key and/or sys_id found in configuration')
                return

            headers = {
                "X-Pvoutput-Apikey": self.config.get('pvoutput', 'api_key'),
                "X-Pvoutput-SystemId": str(self.config.get('pvoutput', 'sys_id')),
                "Content-type": "application/x-www-form-urlencoded",
                "Accept": "text/plain"
            }

            # see: https://pvoutput.org/help.html
            # see: https://pvoutput.org/help.html#api-addstatus
            data = {
                'd': reporttime.strftime('%Y%m%d'),
                't': reporttime.strftime('%H:%M'),
                'v1': str(float(msg['total_energy']) * 1000),
                'v2': str(float(msg['current_power']) * 1000),
                'c1': 1
            }

            if self.config.getboolean('pvoutput', 'use_temperature', fallback=False):
                weather = self.get_weather(self.hass_api)

                data['v5'] = str(weather['main']['temp'])

            encoded = urllib.parse.urlencode(data)

            self.logger.debug(json.dumps(data, indent=2))

            r = requests.post(
                "http://pvoutput.org/service/r2/addstatus.jsp", data=encoded, headers=headers)

            r.raise_for_status()


        except requests.exceptions.RequestException as err:
            hybridlogger.ha_log(self.logger, self.hass_api, "WARNING",f"Unhandled request error: {err}")
        except requests.exceptions.HTTPError as errh:
            hybridlogger.ha_log(self.logger, self.hass_api, "WARNING",f"Http error: {errh}")
        except requests.exceptions.ConnectionError as errc:
            hybridlogger.ha_log(self.logger, self.hass_api, "WARNING",f"Connection error: {errc}")
        except requests.exceptions.Timeout as errt:
            hybridlogger.ha_log(self.logger, self.hass_api, "WARNING",f"Timeout error: {errt}")  
        except Exception as e:
            hybridlogger.ha_log(self.logger, self.hass_api, "ERROR",e)
