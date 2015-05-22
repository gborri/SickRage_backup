# Author: Mr_Orange <mr_orange@hotmail.it>
# URL: http://code.google.com/p/sickbeard/
#
# This file is part of SickRage.
#
# SickRage is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SickRage is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickRage.  If not, see <http://www.gnu.org/licenses/>.

import re
import json
from base64 import b64encode

import sickbeard
from sickbeard import logger
from sickbeard.clients.generic import GenericClient
from sickbeard.name_parser.parser import NameParser, InvalidNameException, InvalidShowException


class TransmissionAPI(GenericClient):
    def __init__(self, host=None, username=None, password=None):

        super(TransmissionAPI, self).__init__('Transmission', host, username, password)

        if not self.host.endswith('/'):
            self.host = self.host + '/'

        if self.rpcurl.startswith('/'):
            self.rpcurl = self.rpcurl[1:]

        if self.rpcurl.endswith('/'):
            self.rpcurl = self.rpcurl[:-1]

        self.url = self.host + self.rpcurl + '/rpc'

    def _get_auth(self):

        post_data = json.dumps({'method': 'session-get', })

        try:
            self.response = self.session.post(self.url, data=post_data.encode('utf-8'), timeout=120,
                                              verify=sickbeard.TORRENT_VERIFY_CERT)
            self.auth = re.search('X-Transmission-Session-Id:\s*(\w+)', self.response.text).group(1)
        except:
            return None

        self.session.headers.update({'x-transmission-session-id': self.auth})

        #Validating Transmission authorization
        post_data = json.dumps({'arguments': {},
                                'method': 'session-get',
        })
        self._request(method='post', data=post_data)

        return self.auth

    def _add_torrent_uri(self, result):

        arguments = {}

        arguments['filename'] = result.url

        self.manage_single_episode(result, arguments)

        return True

    def _add_torrent_file(self, result):

        arguments = {}

        arguments['metainfo'] = b64encode(result.content)

        self.manage_single_episode(result, arguments)

        return True

    def sinlge_episode_enable(self):

        return True

    def manage_single_episode(self, result, add_arguments):

        is_not_downloading = False

        if not self._torrent_is_downloading(result):

            add_arguments['paused'] = 1
            add_arguments['download-dir'] = sickbeard.TORRENT_PATH

            post_data = json.dumps({'arguments': add_arguments,
                                    'method': 'torrent-add',
            })
            self._request(method='post', data=post_data)

            if not self.response.json()['result'] == "success":
                return False

            is_not_downloading = True

        file_list = self._get_file_list_in_torrent(result)

        if not file_list:
            self._manage_trasmission_error(result, add_arguments)

        wantedFile = []
        unwantedFile =[]

        index = 0
        for name_file in file_list['arguments']['torrents'][0]['files']:
            try:
                if '/' in name_file["name"]:
                    name_file["name"] = name_file["name"].split('/')[1]
                myParser = NameParser(showObj=result.show, convert=True)
                parse_result = myParser.parse(name_file["name"])
            except InvalidNameException:
                logger.log(u"Unable to parse the filename " + str(name_file["name"]) + " into a valid episode", logger.DEBUG)
                return True
            except InvalidShowException:
                logger.log(u"Unable to parse the filename " + str(name_file["name"]) + " into a valid show", logger.DEBUG)
                return True 

            if not parse_result or not parse_result.series_name:
                continue

            wanted = False
            for epObj in result.episodes:
                if epObj.episode in parse_result.episode_numbers and epObj.season == parse_result.season_number:
                    wantedFile.append(index)
                    wanted = True
                    break

            if not wanted:
                unwantedFile.append(index)

            index += 1

        if is_not_downloading:

            if unwantedFile:

                self.remove_torrent_downloaded(result.hash)

                add_arguments['files-unwanted'] = unwantedFile
                add_arguments['paused'] = 1 if sickbeard.TORRENT_PAUSED else 0
                add_arguments['download-dir'] = sickbeard.TORRENT_PATH

                post_data = json.dumps({'arguments': add_arguments,
                            'method': 'torrent-add',
                })

                self._request(method='post', data=post_data)

                if not self.response.json()['result'] == "success":
                    self._manage_trasmission_error(result, add_arguments)
            else

                arguments = {'ids': [result.hash]
                }

                post_data = json.dumps({'arguments': arguments,
                            'method': 'torrent-start-now'
                })

                self._request(method='post', data=post_data)

                if not self.response.json()['result'] == "success":
                    self._manage_trasmission_error(result, arguments)
                

        else:

            if wantedFile:

                arguments = {'ids': [result.hash],
                             'files-wanted': wantedFile
                }

                post_data = json.dumps({'arguments': arguments,
                            'method': 'torrent-set'
                })

                self._request(method='post', data=post_data)

                if not self.response.json()['result'] == "success":
                    self._manage_trasmission_error(result, arguments)

        return True

    def _manage_trasmission_error(self, result, add_arguments):

        self.remove_torrent_downloaded(result.hash)

        add_arguments['paused'] = 1 if sickbeard.TORRENT_PAUSED else 0
        add_arguments['download-dir'] = sickbeard.TORRENT_PATH

        post_data = json.dumps({'arguments': add_arguments,
                                'method': 'torrent-add',
        })
        self._request(method='post', data=post_data)

        if not self.response.json()['result'] == "success":
            return False

    def _get_file_list_in_torrent (self, result):

        arguments = {'ids': [result.hash],
                     'fields': ["files"]
        }
        post_data = json.dumps({'arguments': arguments,
                            'method': 'torrent-get',
        })
        self._request(method='post', data=post_data)

        if self.response.json()['result'] == "success":
            return self.response.json()
        else:
            return []

    def _set_torrent_ratio(self, result):

        ratio = None
        if result.ratio:
            ratio = result.ratio

        mode = 0
        if ratio:
            if float(ratio) == -1:
                ratio = 0
                mode = 2
            elif float(ratio) >= 0:
                ratio = float(ratio)
                mode = 1  # Stop seeding at seedRatioLimit

        arguments = {'ids': [result.hash],
                     'seedRatioLimit': ratio,
                     'seedRatioMode': mode
        }
        post_data = json.dumps({'arguments': arguments,
                                'method': 'torrent-set',
        })
        self._request(method='post', data=post_data)

        return self.response.json()['result'] == "success"

    def _set_torrent_seed_time(self, result):

        if sickbeard.TORRENT_SEED_TIME and sickbeard.TORRENT_SEED_TIME != -1:
            time = int(60 * float(sickbeard.TORRENT_SEED_TIME))
            arguments = {'ids': [result.hash],
                         'seedIdleLimit': time,
                         'seedIdleMode': 1
            }

            post_data = json.dumps({'arguments': arguments,
                                'method': 'torrent-set',
            })
            self._request(method='post', data=post_data)

            return self.response.json()['result'] == "success"
        else:
            return True

    def _set_torrent_priority(self, result):

        arguments = {'ids': [result.hash]}

        if result.priority == -1:
            arguments['priority-low'] = []
        elif result.priority == 1:
            # set high priority for all files in torrent
            arguments['priority-high'] = []
            # move torrent to the top if the queue
            arguments['queuePosition'] = 0
            if sickbeard.TORRENT_HIGH_BANDWIDTH:
                arguments['bandwidthPriority'] = 1
        else:
            arguments['priority-normal'] = []

        post_data = json.dumps({'arguments': arguments,
                                'method': 'torrent-set',
                                })
        self._request(method='post', data=post_data)

        return self.response.json()['result'] == "success"

    def _torrent_is_downloading(self, result):

        arguments = { 'ids': [result.hash],
                      'fields': [ "id", "name", "hashString"]
                      }
        post_data = json.dumps({ 'arguments': arguments,
                                 'method': 'torrent-get',
                                 })
        self._request(method='post', data=post_data)

        if self.response.json()['result'] == "success" and self.response.json()['arguments']['torrents']:
            return True
        else:
            return False

    def remove_torrent_downloaded(self,hash):

        arguments = { 'ids': [hash]
                      }
        post_data = json.dumps({'arguments': arguments,
                                'method': 'torrent-remove',
                                })
        self._request(method='post', data=post_data)

        return self.response.json()['result'] == "success"

api = TransmissionAPI()
