content = open('app/static/css/style.css', encoding='utf-8').read()

old = '.chart-card {\n  background: var(--card-bg);\n  border-radius: 12px;\n  border: 1px solid var(--border-color);\n  padding: 18px 20px;\n}'

new = '''.chart-card {
  background: #ffffff;
  border-radius: 12px;
  border: 1px solid #e8ede8;
  border-top: 3px solid #27ae60;
  padding: 20px 22px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}'''

result = content.replace(old, new)
if result == content:
    print("ERROR: not found")
else:
    open('app/static/css/style.css', 'w', encoding='utf-8').write(result)
    print("Done")
