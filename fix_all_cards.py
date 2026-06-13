import re

# Fix style.css
content = open('app/static/css/style.css', encoding='utf-8').read()

# Fix chart-card (still using var(--card-bg))
content = content.replace(
    '.chart-card {\n  background: var(--card-bg);\n  border-radius: 12px;\n  border: 1px solid var(--border-color);\n  padding: 18px 20px;\n  height: 100%;\n}',
    '''.chart-card {
  background: #ffffff;
  border-radius: 12px;
  border: 1px solid #e8ede8;
  border-top: 3px solid #27ae60;
  padding: 20px 22px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}'''
)

# Fix gc-card
content = content.replace(
    '.gc-card { background: var(--card-bg); border-radius: 12px; border: 1px solid var(--border-color); padding: 20px 22px; height: 100%; }',
    '''.gc-card {
  background: #ffffff;
  border-radius: 12px;
  border: 1px solid #e8ede8;
  border-top: 3px solid #27ae60;
  padding: 20px 22px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}'''
)

# Fix gc-card-title
content = content.replace(
    '.gc-card-title { font-size: 14px; font-weight: 700; color: var(--text-primary); margin-bottom: 4px; }',
    '''.gc-card-title {
  font-size: 11px;
  font-weight: 700;
  color: #4a7c59;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 4px;
  padding-bottom: 10px;
  border-bottom: 1px solid #e8ede8;
}'''
)

# Fix rel-card in style.css
content = re.sub(
    r'\.rel-card \{[^}]+\}',
    '''.rel-card {
  background: #ffffff;
  border-radius: 12px;
  border: 1px solid #e8ede8;
  border-top: 3px solid #27ae60;
  padding: 20px 22px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  height: 100%;
}''',
    content
)

# Fix rel-card-title in style.css
content = content.replace(
    '.rel-card-title { font-size: 13px; font-weight: 700; color: var(--text-primary); margin-bottom: 14px; }',
    '''.rel-card-title {
  font-size: 11px;
  font-weight: 700;
  color: #4a7c59;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid #e8ede8;
}'''
)

open('app/static/css/style.css', 'w', encoding='utf-8').write(content)
print("style.css done")

# Fix reliability.css
rc = open('app/static/css/reliability.css', encoding='utf-8').read()

rc = re.sub(
    r'\.rel-card \{[^}]+\}',
    '''.rel-card {
  background: #ffffff;
  border-radius: 12px;
  border: 1px solid #e8ede8;
  border-top: 3px solid #27ae60;
  padding: 20px 22px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  height: 100%;
}''',
    rc
)

rc = re.sub(
    r'\.rel-card-title \{[^}]+\}',
    '''.rel-card-title {
  font-size: 11px;
  font-weight: 700;
  color: #4a7c59;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid #e8ede8;
}''',
    rc
)

open('app/static/css/reliability.css', 'w', encoding='utf-8').write(rc)
print("reliability.css done")
