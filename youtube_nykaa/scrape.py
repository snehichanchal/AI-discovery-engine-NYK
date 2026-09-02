import json
import csv
import yt_dlp
from itertools import islice
from youtube_comment_downloader import YoutubeCommentDownloader, SORT_BY_RECENT
from youtube_transcript_api import YouTubeTranscriptApi
import datetime

def get_channel_videos(channel_url, max_videos=20):
    print(f"Fetching videos from channel: {channel_url}...")
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'playlistend': max_videos,
    }
    video_ids = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)
            if 'entries' in info:
                for entry in info['entries']:
                    video_ids.append({
                        'id': entry['id'],
                        'title': entry.get('title', 'Unknown Title'),
                        'url': f"https://www.youtube.com/watch?v={entry['id']}"
                    })
    except Exception as e:
        print(f"Error fetching channel videos: {e}")
        
    return video_ids

def scrape_comments(video_ids, max_total_comments=100):
    print(f"Extracting comments from {len(video_ids)} videos...")
    downloader = YoutubeCommentDownloader()
    
    all_comments = []
    
    for video in video_ids:
        if len(all_comments) >= max_total_comments:
            break
            
        print(f"Fetching comments for video: {video['title']} ({video['url']})")
        try:
            # Fetch transcript
            transcript_text = "Transcript not available"
            try:
                transcript_obj = YouTubeTranscriptApi().fetch(video['id'])
                transcript_text = " ".join([snippet['text'] for snippet in transcript_obj])
            except Exception as e:
                pass # Many shorts do not have transcripts, ignore error quietly

            # Sort by recent to get the latest comments
            comments = downloader.get_comments_from_url(video['url'], sort_by=SORT_BY_RECENT)
            
            # Fetch up to 20 comments per video to ensure variety, unless fewer needed
            for comment in islice(comments, 20):
                all_comments.append({
                    'platform': 'YouTube',
                    'video_title': video['title'],
                    'video_url': video['url'],
                    'author': comment.get('author', 'Unknown'),
                    'content': comment.get('text', ''),
                    'comment_id': comment.get('cid', ''),
                    'likes': comment.get('votes', 0),
                    'time_parsed': comment.get('time_parsed', ''),
                    'video_transcript': transcript_text,
                    'scraped_at': datetime.datetime.now().isoformat()
                })
                
                if len(all_comments) >= max_total_comments:
                    break
                    
        except Exception as e:
            print(f"Error fetching comments for {video['id']}: {e}")
            
    return all_comments[:max_total_comments]

def main():
    channel_url = "https://www.youtube.com/@nykaafashionofficial/shorts"
    
    # Fetch recent videos/shorts from the channel
    videos = get_channel_videos(channel_url, max_videos=300)
    
    if not videos:
        print("No videos found from the channel.")
        return
        
    # Scrape exactly 100 latest comments across these videos
    comments = scrape_comments(videos, max_total_comments=100)
    
    print("-" * 50)
    print(f"Successfully collected {len(comments)} latest comments from the YouTube channel.")
    
    if comments:
        # Save to JSON
        json_filename = 'nykaa_youtube_comments.json'
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(comments, f, indent=4, ensure_ascii=False)
        print(f"Data saved to {json_filename}")
        
        # Save to CSV
        csv_filename = 'nykaa_youtube_comments.csv'
        keys = comments[0].keys()
        with open(csv_filename, 'w', newline='', encoding='utf-8') as f:
            dict_writer = csv.DictWriter(f, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(comments)
        print(f"Data saved to {csv_filename}")
    else:
        print("No comments found.")

if __name__ == "__main__":
    main()
