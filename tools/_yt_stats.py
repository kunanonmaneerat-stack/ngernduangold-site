# Read-only: fetch stats for recent uploads (cheap: ~3 quota units)
import json
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

ROOT = Path(r"C:\Users\nL_ku\ngernduangold-site")
creds = Credentials.from_authorized_user_file(str(ROOT / "secrets" / "yt_token.json"))
yt = build("youtube", "v3", credentials=creds)

ch = yt.channels().list(part="contentDetails,statistics", mine=True).execute()
item = ch["items"][0]
uploads = item["contentDetails"]["relatedPlaylists"]["uploads"]
print("CHANNEL subs=", item["statistics"].get("subscriberCount"), "views=", item["statistics"].get("viewCount"))

pl = yt.playlistItems().list(part="contentDetails,snippet", playlistId=uploads, maxResults=20).execute()
ids = [x["contentDetails"]["videoId"] for x in pl.get("items", [])]
if ids:
    vids = yt.videos().list(part="snippet,statistics,status", id=",".join(ids)).execute()
    for v in vids.get("items", []):
        s = v.get("statistics", {})
        st = v.get("status", {})
        title = v["snippet"]["title"][:45]
        print(f"{v['id']} | {st.get('privacyStatus')} | views={s.get('viewCount','0')} likes={s.get('likeCount','0')} | {title}")
