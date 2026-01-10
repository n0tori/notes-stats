#!/usr/bin/env python3
import subprocess
import os
from datetime import datetime, timedelta
from collections import defaultdict

NOTES_DIR = "/var/www/nextcloud/data/user/files/Notes"
TEMPLATE_PATH = "/usr/local/bin/notes-template.html"
OUTPUT_PATH = "/var/www/website/notes.html"

def run_cmd(cmd):
  result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=NOTES_DIR)
  return result.stdout.strip()

def count_pattern(pattern):
  cmd = f"grep -roh '{pattern}' --include='*.md' . | wc -l"
  return int(run_cmd(cmd) or 0)

def get_file_list():
  cmd = "find . -type f -name '*.md'"
  files = run_cmd(cmd).split('\n')
  return [f for f in files if f]

def calculate_basic_stats():
  stats = {}

  stats['total_notes'] = int(run_cmd("find . -type f -name '*.md' | wc -l"))
  stats['total_words'] = int(run_cmd("find . -type f -name '*.md' -exec wc -w {} + | tail -1 | awk '{print $1}'"))
  stats['total_lines'] = int(run_cmd("find . -type f -name '*.md' -exec wc -l {} + | tail -1 | awk '{print $1}'"))
  du_output = run_cmd("du -sh .")
  stats['disk_usage'] = du_output.split()[0]
  stats['avg_words'] = stats['total_words'] // stats['total_notes']
  stats['avg_lines'] = stats['total_lines'] // stats['total_notes']
  stats['total_vaults'] = int(run_cmd("find . -maxdepth 1 -mindepth 1 -type d ! -name '.*' | wc -l"))
  return stats

def calculate_content_stats():
  stats = {}
  stats['internal_links'] = count_pattern('\\[\\[[^]]*\\]\\]')
  stats['external_urls'] = count_pattern('https\\?://[^[:space:]]\\+')
  stats['images'] = count_pattern('!\\[\\[[^]]*\\]\\]') + count_pattern('!\\[[^]]*\\]([^)]*)')
  stats['code_blocks'] = count_pattern('```') // 2
  stats['math_expr'] = count_pattern('\\$\\$[^$]*\\$\\$') + count_pattern('\\$[^$]*\\$')
  return stats

def calculate_markdown_stats():
  stats = {}
  stats['h1'] = count_pattern('^# ')
  stats['h2'] = count_pattern('^## ')
  stats['h3'] = count_pattern('^### ')
  stats['h4'] = count_pattern('^#### ')
  stats['lists'] = count_pattern('^[[:space:]]*[-*] ') + count_pattern('^[[:space:]]*[0-9]\\+\\. ')
  stats['blockquotes'] = count_pattern('^> ')
  stats['tables'] = count_pattern('^|.*|$') // 3  # Estimate: header, separator, data
  stats['hr'] = count_pattern('^---$') + count_pattern('^\\*\\*\\*$')
  return stats

def calculate_task_stats():
  stats = {}
  total = count_pattern('\\- \\[[ x]\\]')
  stats['total_tasks'] = total
  completed = count_pattern('\\- \\[x\\]')
  stats['tasks_completed'] = completed
  stats['tasks_unchecked'] = total - completed
  if total > 0:
    stats['task_completion'] = (completed * 100) // total
  else:
    stats['task_completion'] = 0

  stats['task_completion_angle'] = (stats['task_completion'] * 360) // 100

  return stats

def calculate_temporal_stats():
  stats = {}
  cmd = "find . -type f -name '*.md' -printf '%T@\\n' | sort -n | tail -1"
  last_edit_ts = run_cmd(cmd)
  if last_edit_ts:
    last_edit = datetime.fromtimestamp(float(last_edit_ts))
    stats['days_since_last_edit'] = (datetime.now() - last_edit).days
  else:
    stats['days_since_last_edit'] = 0

  monthly_counts = []
  now = datetime.now()

  for i in range(5, -1, -1):
    target_month = now - timedelta(days=30*i)
    month_start = target_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month_start.month == 12:
      month_end = month_start.replace(year=month_start.year+1, month=1)
    else:
      month_end = month_start.replace(month=month_start.month+1)

    start_ts = int(month_start.timestamp())
    end_ts = int(month_end.timestamp())

    cmd = f"find . -type f -name '*.md' -newermt '@{start_ts}' ! -newermt '@{end_ts}' | wc -l"
    count = int(run_cmd(cmd) or 0)

    monthly_counts.append({'month': month_start.strftime('%b %Y'), 'count': count})

  stats['monthly_activity'] = monthly_counts

  dow_counts = defaultdict(int)
  files = get_file_list()

  for file in files:
    if not file:
      continue
    cmd = f"stat -c %Y '{file}'"
    ts = run_cmd(cmd)
    if ts:
      dt = datetime.fromtimestamp(int(ts))
      dow = dt.strftime('%a')
      dow_counts[dow] += 1

  days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
  stats['day_of_week'] = [{'day': day, 'count': dow_counts.get(day, 0)} for day in days]

  return stats

def calculate_length_distribution():
  files = get_file_list()
  buckets = [0, 0, 0, 0, 0, 0]  # 0-100, 100-500, 500-1k, 1k-2k, 2k-5k, 5k+

  for file in files:
    if not file:
      continue
    cmd = f"wc -w '{file}' | awk '{{print $1}}'"
    words = int(run_cmd(cmd) or 0)

    if words < 100:
      buckets[0] += 1
    elif words < 500:
      buckets[1] += 1
    elif words < 1000:
      buckets[2] += 1
    elif words < 2000:
      buckets[3] += 1
    elif words < 5000:
      buckets[4] += 1
    else:
      buckets[5] += 1

  return buckets

def generate_html():
  with open(TEMPLATE_PATH, 'r') as f:
    html = f.read()

  basic = calculate_basic_stats()
  if basic is None:
    print("No markdown files found")
    return

  content = calculate_content_stats()
  markdown = calculate_markdown_stats()
  tasks = calculate_task_stats()
  temporal = calculate_temporal_stats()
  length_dist = calculate_length_distribution()

  # Basic stats
  html = html.replace('{{TOTAL_NOTES}}', str(basic['total_notes']))
  html = html.replace('{{TOTAL_WORDS}}', f"{basic['total_words']:,}")
  html = html.replace('{{TOTAL_LINES}}', f"{basic['total_lines']:,}")
  html = html.replace('{{DISK_USAGE}}', basic['disk_usage'])
  html = html.replace('{{AVG_WORDS}}', str(basic['avg_words']))
  html = html.replace('{{AVG_LINES}}', str(basic['avg_lines']))
  html = html.replace('{{TOTAL_VAULTS}}', str(basic['total_vaults']))

  # Task stats with ASCII progress bar
  html = html.replace('{{TOTAL_TASKS}}', str(tasks['total_tasks']))
  html = html.replace('{{TASKS_COMPLETED}}', str(tasks['tasks_completed']))
  html = html.replace('{{TASKS_UNCHECKED}}', str(tasks['tasks_unchecked']))
  html = html.replace('{{TASK_COMPLETION}}', str(tasks['task_completion']))

  # ASCII progress bar (20 chars)
  filled = (tasks['task_completion'] * 20) // 100
  progress_bar = '=' * filled + '-' * (20 - filled)
  html = html.replace('{{TASK_PROGRESS_BAR}}', progress_bar)

  # Content stats
  html = html.replace('{{INTERNAL_LINKS}}', str(content['internal_links']))
  html = html.replace('{{EXTERNAL_URLS}}', str(content['external_urls']))
  html = html.replace('{{IMAGES}}', str(content['images']))
  html = html.replace('{{CODE_BLOCKS}}', str(content['code_blocks']))
  html = html.replace('{{MATH_EXPR}}', str(content['math_expr']))

  # Markdown stats
  html = html.replace('{{H1_COUNT}}', str(markdown['h1']))
  html = html.replace('{{H2_COUNT}}', str(markdown['h2']))
  html = html.replace('{{H3_COUNT}}', str(markdown['h3']))
  html = html.replace('{{H4_COUNT}}', str(markdown['h4']))
  html = html.replace('{{LISTS}}', str(markdown['lists']))
  html = html.replace('{{BLOCKQUOTES}}', str(markdown['blockquotes']))
  html = html.replace('{{TABLES}}', str(markdown['tables']))
  html = html.replace('{{HR_COUNT}}', str(markdown['hr']))

  # Temporal stats
  html = html.replace('{{DAYS_SINCE_LAST_EDIT}}', str(temporal['days_since_last_edit']))

  # Monthly activity calendar grid
  monthly_html = ""
  for month_data in temporal['monthly_activity']:
    monthly_html += f'''          <div class="calendar-month">
            <div class="month-label">{month_data['month']}</div>
            <div class="month-value">{month_data['count']}</div>
          </div>\n'''
  html = html.replace('{{MONTHLY_ACTIVITY}}', monthly_html)

  # Day of week ASCII bars
  dow_max = max([d['count'] for d in temporal['day_of_week']]) or 1
  most_active_day = max(temporal['day_of_week'], key=lambda x: x['count'])

  dow_bars = ""
  for dow_data in temporal['day_of_week']:
    bar_len = (dow_data['count'] * 30) // dow_max if dow_max > 0 else 0
    bar = '█' * bar_len
    dow_bars += f"{dow_data['day']}: {bar} {dow_data['count']}\n"

  html = html.replace('{{DAY_OF_WEEK_BARS}}', dow_bars.strip())
  html = html.replace('{{MOST_ACTIVE_DAY}}', most_active_day['day'])
  html = html.replace('{{MOST_ACTIVE_DAY_COUNT}}', str(most_active_day['count']))

  # Length distribution with metrics
  ranges = ['0-100', '100-500', '500-1k', '1k-2k', '2k-5k', '5k+']
  length_html = ""
  for i, count in enumerate(length_dist):
    length_html += f'          <li><span class="label">{ranges[i]} words</span> <span class="value">{count} notes</span></li>\n'
  html = html.replace('{{LENGTH_DISTRIBUTION}}', length_html)

  max_idx = length_dist.index(max(length_dist))
  html = html.replace('{{MOST_COMMON_BRACKET}}', ranges[max_idx])
  html = html.replace('{{MOST_COMMON_COUNT}}', str(length_dist[max_idx]))

  # Find longest and shortest with actual notes
  longest_idx = next((i for i in range(5, -1, -1) if length_dist[i] > 0), 0)
  shortest_idx = next((i for i in range(6) if length_dist[i] > 0), 0)
  html = html.replace('{{LONGEST_BRACKET}}', ranges[longest_idx])
  html = html.replace('{{LONGEST_COUNT}}', str(length_dist[longest_idx]))
  html = html.replace('{{SHORTEST_BRACKET}}', ranges[shortest_idx])
  html = html.replace('{{SHORTEST_COUNT}}', str(length_dist[shortest_idx]))

  # Footer metadata
  html = html.replace('{{LAST_UPDATED}}', datetime.now().strftime('%d/%m/%Y'))

  with open(OUTPUT_PATH, 'w') as f:
    f.write(html)

  file_size = run_cmd(f"ls -lh '{OUTPUT_PATH}' | awk '{{print $5}}'")

  with open(OUTPUT_PATH, 'r') as f:
    html = f.read()
  html = html.replace('{{FILE_SIZE}}', file_size)
  with open(OUTPUT_PATH, 'w') as f:
    f.write(html)

  print(f"Generated {OUTPUT_PATH}")

if __name__ == "__main__":
  generate_html()
