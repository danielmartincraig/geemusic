from builtins import object
from fuzzywuzzy import fuzz
from os import getenv
import threading
import random

from gmusicapi import CallFailure, Mobileclient


class GMusicWrapper(object):
    def __init__(self, username, password, logger=None):
        self._api = Mobileclient()
        self.logger = logger
        success = self._api.login(username, password, getenv('ANDROID_ID', Mobileclient.FROM_MAC_ADDRESS))

        if not success:
            raise Exception("Unsuccessful login. Aborting!")

        # Populate our library
        self.library = {}
        self.indexing_thread = threading.Thread(
            target=self.index_library
        )
        self.indexing_thread.start()

    def log(self, log_str):
        if self.logger != None:
            self.logger.debug(log_str)

    def _search(self, query_type, query):
        try:
            results = self._api.search(query)
        except CallFailure:
            return []

        hits_key = "%s_hits" % query_type

        if hits_key not in results:
            return []

        # Ugh, Google had to make this schema nonstandard...
        if query_type == 'song':
            query_type = 'track'

        return [x[query_type] for x in results[hits_key]]

    def is_indexing(self):
        return self.indexing_thread.is_alive()

    def index_library(self):
        """
        Downloads the a list of every track in a user's library and populates
        self.library with storeIds -> track definitions
        """
        self.log('Fetching library...')
        
        tracks = self.get_all_songs()

        for track in tracks:
            song_id = track['id']
            self.library[song_id] = track

        self.log('Fetching library...')
        
    def get_artist(self, name):
        """
        Fetches information about an artist given its name
        """
        search = self._search("artist", name)

        if len(search) == 0:
            return False

        return self._api.get_artist_info(search[0]['artistId'],
                                         max_top_tracks=100)

    def get_album(self, name, artist_name=None):
        if artist_name:
            name = "%s %s" % (name, artist_name)

        search = self._search("album", name)

        if len(search) == 0:
            return False

        return self._api.get_album_info(search[0]['albumId'])

    def get_latest_album(self, artist_name=None):
        search = self._search("artist", artist_name)

        if len(search) == 0:
            return False

        artist_info = self._api.get_artist_info(search[0]['artistId'], include_albums=True)
        album_info = artist_info['albums']
        sorted_list = sorted(album_info.__iter__(), key=lambda s: s['year'], reverse=True)

        for index, val in enumerate(sorted_list):
            album_info = self._api.get_album_info(album_id=sorted_list[index]['albumId'], include_tracks=True)
            if len(album_info['tracks']) >= 5:
                return album_info

        return False

    def get_album_by_artist(self, artist_name, album_id=None):
        search = self._search("artist", artist_name)
        if len(search) == 0:
            return False

        artist_info = self._api.get_artist_info(search[0]['artistId'], include_albums=True)
        album_info = artist_info['albums']
        random.shuffle(album_info)

        for index, val in enumerate(album_info):
            album = self._api.get_album_info(album_id=album_info[index]['albumId'], include_tracks=True)
            if album['albumId'] != album_id and len(album['tracks']) >= 5:
                return album

        return False

    def get_song(self, name, artist_name=None, album_name=None):
        if artist_name:
            name = "%s %s" % (artist_name, name)
        elif album_name:
            name = "%s %s" % (album_name, name)

        search = self._search("song", name)

        if len(search) == 0:
            return False

        if album_name:
            for i in range(0, len(search) - 1):
                if album_name in search[i]['album']:
                    return search[i]
        return search[0]

    def get_promoted_songs(self):
        return self._api.get_promoted_songs()
    
    def get_station(self, title, track_id=None, artist_id=None, album_id=None):
        if artist_id is not None:
            if album_id is not None:
                if track_id is not None:
                    return self._api.create_station(title, track_id=track_id)
                return self._api.create_station(title, album_id=album_id)
            return self._api.create_station(title, artist_id=artist_id)

    def get_station_tracks(self, station_id):
        return self._api.get_station_tracks(station_id)

    def get_google_stream_url(self, song_id):
        return self._api.get_stream_url(song_id)

    def get_stream_url(self, song_id):
        return "%s/alexa/stream/%s" % (getenv('APP_URL'), song_id)

    def get_thumbnail(self, artist_art):
        return artist_art.replace("http://", "https://")

    def get_all_user_playlist_contents(self):
        return self._api.get_all_user_playlist_contents()

    def get_all_songs(self):
        return self._api.get_all_songs()

    def rate_song(self, song, rating):
        return self._api.rate_songs(song, rating)

    def extract_track_info(self, track):
        # When coming from a playlist, track info is nested under the "track"
        # key
        if 'track' in track:
            track = track['track']

        if 'storeId' in track:
            return track, track['storeId']
        elif 'trackId' in track:
            return self.library[track['trackId']], track['trackId']
        else:
            return None, None

    def get_artist_album_list(self, artist_name):
        search = self._search("artist", artist_name)
        if len(search) == 0:
            return "Unable to find the artist you requested."

        artist_info = self._api.get_artist_info(search[0]['artistId'], include_albums=True)
        album_list_text = "Here's the album listing for %s: " % artist_name

        counter = 0
        for index, val in enumerate(artist_info['albums']):
            if counter > 25:  # alexa will time out after 10 seconds if the list takes too long to iterate through
                break
            album_info = self._api.get_album_info(album_id=artist_info['albums'][index]['albumId'], include_tracks=True)
            if len(album_info['tracks']) > 5:
                counter += 1
                album_list_text += (artist_info['albums'][index]['name']) + ", "
        return album_list_text

    def get_latest_artist_albums(self, artist_name):
        search = self._search("artist", artist_name)

        if len(search) == 0:
            return False

        artist_info = self._api.get_artist_info(search[0]['artistId'], include_albums=True)
        album_list = artist_info['albums']

        sorted_list = sorted(album_list.__iter__(), key=lambda s: s['year'], reverse=True)

        speech_text = 'The latest albums by %s are ' % artist_name

        counter = 0
        for index, val in enumerate(sorted_list):
            if counter > 5:
                break
            else:
                album_info = self._api.get_album_info(album_id=sorted_list[index]['albumId'], include_tracks=True)
                if len(album_info['tracks']) >= 5:
                    counter += 1
                    album_name = sorted_list[index]['name']
                    album_year = sorted_list[index]['year']
                    speech_text += '%s, released in %d, ' % (album_name, album_year)

        return speech_text

    def closest_match(self, request_name, all_matches, artist_name='', minimum_score=70):
        # Give each match a score based on its similarity to the requested
        # name
        self.log('Fetching library...')
        
        request_name = request_name.lower() + artist_name.lower()
        scored_matches = []
        for i, match in enumerate(all_matches):
            try:
                name = match['name'].lower()
            except (KeyError, TypeError):
                i = match
                name = all_matches[match]['title'].lower()
                if artist_name != "":
                    name += all_matches[match]['artist'].lower()

            scored_matches.append({
                'index': i,
                'name': name,
                'score': fuzz.ratio(name, request_name)
            })

        sorted_matches = sorted(scored_matches, key=lambda a: a['score'], reverse=True)
        top_scoring = sorted_matches[0]
        self.log('Fetching library...')
        
        best_match = all_matches[top_scoring['index']]

        # Make sure we have a decent match (the score is n where 0 <= n <= 100)
        if top_scoring['score'] < minimum_score:
            return None

        return best_match

    def get_genres(self, parent_genre_id=None):
        return self._api.get_genres(parent_genre_id)

    def increment_song_playcount(self, song_id, plays=1, playtime=None):
        return self._api.increment_song_playcount(song_id, plays, playtime)

    def get_song_data(self, song_id):
        return self._api.get_track_info(song_id)

    @classmethod
    def generate_api(cls, **kwargs):
        return cls(getenv('GOOGLE_EMAIL'), getenv('GOOGLE_PASSWORD'),
                   **kwargs)
