import datetime
import time
from datetime import datetime
import os


kantipur_stream = "https://radio-broadcast.ekantipur.com/stream"
ujalyo_stream = "https://stream-146.zeno.fm/wtuvp08xq1duv"
kantipur_time='18:30'
kantipur_duration_min=30
ujalyo_duration_min=30
ujalyo_time='18:00'

output_dir='radio_recordings'
os.makedirs(output_dir,exist_ok=True)


def record(stream_url,name):
	now=datetime.now()
	date=now.strftime('%Y-%m-%d')
	filename=f"{output_dir}/{name}_{date}.mp3"
	
	print(f'recording {name} to {filename}')

	cmd=[
		"ffmpeg",
		"-y",		
		"-i", stream_url,
		"-t","1800",
		"-acodec",'libmp3lame',
		"-ab","64k",
		filename
	]
	subprocess.run(cmd)

