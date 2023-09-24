import json, requests, time, threading
import tkinter as tk

from youtube_transcript_api import YouTubeTranscriptApi
from youtubesearchpython import Video, ResultMode, Comments

from secrets import natdev_session  # get this string by logging into nat.dev and copying from cookie info

def get_yt_comments(id_or_url, maxcomments=None):
    # from youtubesearchpython import Comments

    """
    max_call_count: if None, will repeat api calls until no more comments; each call retrieves 20 comments
    """

    try:
        comments = Comments(id_or_url)
    except:
        print('Error: could not get comments')
        return []

    # grab comments
    if maxcomments == None:
        while comments.hasMoreComments:
            comments.getNextComments()
    else:
        while len(comments.comments["result"]) < maxcomments and comments.hasMoreComments:
            comments.getNextComments()

    # next, reshape the list so it's prettier, and return

    def get_likes(item):  # returns the amount of likes as an int
        text = item['votes']['simpleText']
        if text == None:
            return 0
        elif 'K' in text:
            return int(float(text.replace('K', '')) * 1000)
        elif 'M' in text:
            return int(float(text.replace('M', '')) * 1000000)
        else:
            return int(text)
    sorted_by_likes = sorted(
        comments.comments['result'],
        key=get_likes,
        reverse=True
    )

    nicer = []
    for comment in sorted_by_likes:
        comment_id = comment['id']
        username = comment['author']['name']
        likes = comment['votes']['simpleText']
        text = comment['content']
        published = comment['published']

        nicer.append({
            'comment_id': comment_id,
            'username': username,
            'likes': likes,
            'text': text,
            'published': published,
        })

    return nicer

def vidinfo(url, get_comments=True):
    # from youtubesearchpython import Video, ResultMode
    video = Video.getInfo(url, mode = ResultMode.json)

    to_return = {
        'title': video['title'],
        'seconds': video['duration']['secondsText'],
        'views': video['viewCount']['text'],
        'description': video['description'],
        'upload_date': video['uploadDate'],
        'category': video['category'],
        'keywords': video['keywords'],
        'link': video['link'],
        'channelname': video['channel']['name'],
        'channellink': video['channel']['link'],
        'channelid': video['channel']['id'],
    }

    if get_comments:
        comments = get_yt_comments(url, 1)
        comments = [c['text'] for c in comments[:10]]
        to_return['comments'] = comments
    print(json.dumps(to_return, indent=4))
    return to_return

def get_transcript(url):
    video_id = url.split('v=')[1]
    t = YouTubeTranscriptApi.get_transcript(video_id)

    class Transcript(list):
        def __init__(self, t):
            super().__init__(t)
            self.duration = t[-1]['start'] + t[-1]['duration']

        def get_timerange(self, start, end):
            # grabs a subset of the transcript, can pass seconds or 'hh:mm:ss' strings
            def t_to_s(t):
                h, m, s = t.split(':')
                return int(h) * 3600 + int(m) * 60 + int(s)
            in_seconds = type(start) in (int, float)
            if not in_seconds:
                start = t_to_s(start)
                end = t_to_s(end)
            subset = [i for i in self if i['start'] >= start and i['start'] <= end]
            lines = [i['text'] for i in subset]
            return '\n'.join(lines)

    return Transcript(t)

def nat_dev(model, prompt, print_func=lambda x:None):
    # prepare request
    url = "https://nat.dev/api/inference/text"
    payload_dict = {
        "prompt": prompt,
        "models": [
            {
                "name": f"openai:{model}",
                "tag": f"openai:{model}",
                "capabilities": ["chat"],
                "provider": "openai",
                "parameters": {
                    "temperature": 0.5,
                    "maximumLength": 400,
                    "topP": 1,
                    "presencePenalty": 0,
                    "frequencyPenalty": 0,
                    "stopSequences": [],
                    "numberOfSamples": 1,
                },
                "enabled": True,
                "selected": True,
            }
        ],
        "stream": True,
    }
    payload = json.dumps(payload_dict)
    session = natdev_session
    headers = {
        "Content-Type": "text/plain;charset=UTF-8",
        "Accept": "*/*",
        "Referer": "https://nat.dev/",
        "Origin": "https://nat.dev",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Cookie": f"__session={session}",
    }
    response = requests.post(url, headers=headers, data=payload, stream=True)
    
    # parse and return
    all_tokens = []
    for line in response.iter_lines():
        if line == b'event:status':
            continue
        else:
            data = str(line, 'utf-8').partition('data:')[2]
            if data == '':
                continue
            token = json.loads(data)['token']
            if token == '[INITIALIZING]':
                continue
            if token == '[COMPLETED]':
                break
            else:
                print_func(token)
                all_tokens.append(token)
    return ''.join(all_tokens)


import tkinter as tk

class BarAdjuster(tk.Tk):
    def __init__(self, url):
        super().__init__()
        self.title('Bar Adjuster')
        self.height = 50
        self.width = 1000
        self.geometry(f'{self.width}x{700}-0+0')
        self.configure(bg='black')
        self.canvas = tk.Canvas(self, width=self.width, height=self.height, bg='black')
        self.canvas.pack()
        self.small_bar = self.canvas.create_rectangle(150, 0, 250, self.height, fill='darkgreen')
        self.canvas.bind('<Button-1>', self._adjust)
        self.canvas.bind('<Button-3>', self._change_center)
        self.bind('<KeyPress-F5>', lambda e: self._on_click())

        self.btn = tk.Button(self, text='click or f5 to use prompt', command=self._on_click)
        self.btn.pack()

        self.entry = tk.Entry(self)
        self.entry.insert(0, 'gpt-3.5-turbo-16k')
        self.entry.pack()

        self.entry2 = tk.Entry(self)
        self.entry2.insert(0, '0:00:00-0:00:10')
        self.entry2.pack()

        self.url = url
        self.info = vidinfo(url)
        self.transcript = get_transcript(url)

        self.model = self.entry.get()

        self.entry2.bind('<Return>', self._entry2_cmd)

        self.text = tk.Text(self, height=30, width=self.width, bg='black', fg='beige', insertbackground='white', font=('Calibri', 14))
        self.text.config(selectbackground=self.text['fg'], selectforeground=self.text['bg'])
        self.text.pack()
    
    def _entry2_cmd(self, event):
        text = self.entry2.get()
        if len(text.split('-')) == 2:
            t0, t1 = text.split('-')
            if len(t0.split(':')) == 3 and len(t1.split(':')) == 3:
                self._change_bar(t0, t1)

    def _adjust(self, event):
        bar_coords = self.canvas.coords(self.small_bar)
        if bar_coords[0] < event.x < bar_coords[2]:
            # click inside the bar
            if abs(event.x - bar_coords[0]) > abs(event.x - bar_coords[2]):
                # click closer to the left side of the bar
                self.canvas.coords(self.small_bar, bar_coords[0], 0, event.x, self.height)
            else:
                # click closer to the right side of the bar
                self.canvas.coords(self.small_bar, event.x, 0, bar_coords[2], self.height)
        else:
            # click outside the bar
            if event.x < self.canvas.coords(self.small_bar)[0]:
                # click to the left of the bar
                self.canvas.coords(self.small_bar, event.x, 0, self.canvas.coords(self.small_bar)[2], self.height)
            elif event.x > self.canvas.coords(self.small_bar)[2]:
                # click to the right of the bar
                self.canvas.coords(self.small_bar, self.canvas.coords(self.small_bar)[0], 0, event.x, self.height)

        # use the bar's new position
        bar_coords = self.canvas.coords(self.small_bar)
        subset = (bar_coords[0] / self.width, bar_coords[2] / self.width)
        self._on_adjust(subset)
    
    def _change_center(self, event):
        bar_coords = self.canvas.coords(self.small_bar)
        center = int( bar_coords[0] + (bar_coords[2]-bar_coords[0])/2 )
        dif = abs(event.x - center)
        if event.x < center:
            x0 = max(0, bar_coords[0] - dif)
            x1 = bar_coords[2] - dif
        else:
            x0 = bar_coords[0] + dif
            x1 = min(self.width, bar_coords[2] + dif)
        self.canvas.coords(self.small_bar, x0, 0, x1, self.height)
        self._on_adjust((x0/self.width, x1/self.width))
    
    def _change_bar(self, t0, t1):
        x0 = t_to_s(t0) / self.transcript.duration * self.width
        x1 = t_to_s(t1) / self.transcript.duration * self.width
        self.canvas.coords(self.small_bar, x0, 0, x1, self.height)
        self._on_adjust((x0/self.width, x1/self.width))

    def _on_adjust(self, subset):
        in_seconds = (int(subset[0]*self.transcript.duration), int(subset[1]*self.transcript.duration))

        self.entry2.delete(0, tk.END)
        self.entry2.insert(0, f'{s_to_t(in_seconds[0])}-{s_to_t(in_seconds[1])}')

        self.transcript_subset = self.transcript.get_timerange(*in_seconds)

        # use the transcript subset and video info to create a prompt
        prompt = '\n'.join([
            'You are a video companion. I will give you info about a video, then a portion of the transcript, then give you a task based on those things.',
            '',
            'Video info:',
            '\n'.join([f'{k}: {v}' for k, v in self.info.items() if k not in []]),
            '',
            f'Transcript portion (from {s_to_t(in_seconds[0])} to {s_to_t(in_seconds[1])}):',
            self.transcript_subset,
            f'(Above is the transcript portion (from {s_to_t(in_seconds[0])} to {s_to_t(in_seconds[1])}):',
            '',
            'Task:',
            "Explain what's being talked about in the transcript portion.",
            '',
        ])
        def remove_invalid_chars(input_str):
            return ''.join(c for c in input_str if '\u0000' <= c <= '\uFFFF')
        prompt = remove_invalid_chars(prompt)
        self.text.delete('1.0', tk.END)
        self.text.insert(tk.END, prompt)
        self.text.see(tk.END)

        print(f'wordcount: {len(prompt.split())}')
        print(f'Transcript portion (from {s_to_t(in_seconds[0])} to {s_to_t(in_seconds[1])}):')
        self.prompt = prompt

        costs = {
            'gpt-3.5-turbo': {
                'prompt': 0.0018,
                'completion': 0.0024,
            },
            'gpt-4': {
                'prompt': 0.036,
                'completion': 0.072,
            },
            'text-davinci-002':{
                'prompt': 0.024,
                'completion': 0.024,
            },
            'text-davinci-003':{
                'prompt': 0.024,
                'completion': 0.024,
            },
            'text-curie-001':{
                'prompt': 0.0024,
                'completion': 0.0024,
            },
        }
        self.model = self.entry.get()
        cost_3 = costs['gpt-3.5-turbo']['prompt']*(len(prompt.split())/1000)
        cost_4 = costs['gpt-4']['prompt']*(len(prompt.split())/1000)
        print(f'3.5 cost: {cost_3}, 4 cost: {cost_4} (excluding completion)')
    
    def _on_click(self):
        self.model = self.entry.get()
        prompt = self.text.get('1.0', tk.END)

        def print_func(x):
            self.text.insert(tk.END, x)
            self.text.see(tk.END)
        thread = threading.Thread(target=nat_dev, args=(self.model, prompt, print_func))
        thread.start()

    def set_adjust_callback(self, callback):
        # callback gets passed a tuple of 2 floats between 0 and 1
        self._on_adjust = callback

def t_to_s(t):
    h, m, s = t.split(':')
    return int(h) * 3600 + int(m) * 60 + int(s)
def s_to_t(s):
    h = s // 3600
    s -= h * 3600
    m = s // 60
    s -= m * 60
    return f'{h}:{m}:{s}'

url = input('url: ')

app = BarAdjuster(url)
app.mainloop()
