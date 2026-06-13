content = open('app/static/css/style.css', encoding='utf-8').read()

old = '.stat-card {'
new = '''.stat-card {
  background: #ffffff !important;
  border-radius: 12px !important;
  border: 1px solid #e8ede8 !important;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06) !important;
  padding: 18px 20px !important;
  /* overrides below are ignored */ display: block !important;'''

# Find and replace just the opening to inject our styles
import re
result = re.sub(
    r'\.stat-card \{[^}]+\}',
    '''.stat-card {
  background: #ffffff;
  border-radius: 12px;
  border: 1px solid #e8ede8;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  padding: 18px 20px;
}''',
    content
)
if result == content:
    print("ERROR: not found")
else:
    open('app/static/css/style.css', 'w', encoding='utf-8').write(result)
    print("Done")
