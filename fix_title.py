content = open('app/static/css/style.css', encoding='utf-8').read()

old = '.chart-card-title { font-size: 13px; font-weight: 700; color: var(--text-primary); margin-bottom: 14px; }'
new = '''.chart-card-title {
  font-size: 11px;
  font-weight: 700;
  color: #4a7c59;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid #e8ede8;
}'''

result = content.replace(old, new)
if result == content:
    print("ERROR: not found")
else:
    open('app/static/css/style.css', 'w', encoding='utf-8').write(result)
    print("Done")
