content = open('app/static/css/style.css', encoding='utf-8').read()

content = content.replace(
    '.filter-btn {\n  padding: 7px 20px; background: var(--accent-green); color: #fff;\n  border: none; border-radius: 8px; font-size: 13px; font-weight: 600;\n  cursor: pointer; transition: background .15s;\n}',
    '.filter-btn {\n  padding: 7px 20px; background: #27ae60; color: #fff;\n  border: none; border-radius: 8px; font-size: 13px; font-weight: 600;\n  cursor: pointer; transition: background .15s;\n}'
)

content = content.replace(
    '.view-btn {\n  padding: 5px 14px; background: var(--accent-green); color: #fff;\n  border: none; border-radius: 6px; font-size: 12px; font-weight: 600;\n  cursor: pointer; transition: background .15s; white-space: nowrap;\n}',
    '.view-btn {\n  padding: 5px 14px; background: #27ae60; color: #fff;\n  border: none; border-radius: 6px; font-size: 12px; font-weight: 600;\n  cursor: pointer; transition: background .15s; white-space: nowrap;\n}'
)

content = content.replace(
    '.export-btn {\n  padding: 6px 16px; background: transparent; color: var(--accent-green);\n  border: 1.5px solid var(--accent-green); border-radius: 8px;\n  font-size: 13px; font-weight: 600; cursor: pointer; transition: all .15s;\n}',
    '.export-btn {\n  padding: 6px 16px; background: #ffffff; color: #27ae60;\n  border: 1.5px solid #27ae60; border-radius: 8px;\n  font-size: 13px; font-weight: 600; cursor: pointer; transition: all .15s;\n}'
)

# Also add --accent-green to the base CSS vars
content = content.replace(
    ':root {',
    ':root {\n    --accent-green: #27ae60;',
    1
)

open('app/static/css/style.css', 'w', encoding='utf-8').write(content)
print("Done")
