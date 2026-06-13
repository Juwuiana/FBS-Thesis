import re
content = open('app/static/css/style.css', encoding='utf-8').read()

card_style = '''
  background: #ffffff;
  border-radius: 12px;
  border: 1px solid #e8ede8;
  border-top: 3px solid #27ae60;
  padding: 20px 22px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
'''

title_style = '''
  font-size: 11px;
  font-weight: 700;
  color: #4a7c59;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid #e8ede8;
'''

# dm-card
content = re.sub(r'\.dm-card \{[^}]+\}', '.dm-card {' + card_style + '}', content)
content = re.sub(r'\.dm-card-title \{[^}]+\}', '.dm-card-title {' + title_style + '}', content)

# audit-card
content = re.sub(r'\.audit-card \{[^}]+\}', '.audit-card {' + card_style + '}', content)

# ps-card
content = re.sub(r'\.ps-card \{[^}]+\}', '.ps-card {' + card_style + '}', content)
content = re.sub(r'\.ps-card-title \{[^}]+\}', '.ps-card-title {' + title_style + '}', content)

# gc-card-subtitle — keep but update color
content = content.replace(
    '.gc-card-subtitle { font-size: 11px; color: var(--text-muted); margin-bottom: 16px; }',
    '.gc-card-subtitle { font-size: 11px; color: #94a3b8; margin-bottom: 16px; }'
)

open('app/static/css/style.css', 'w', encoding='utf-8').write(content)
print("All cards fixed")
