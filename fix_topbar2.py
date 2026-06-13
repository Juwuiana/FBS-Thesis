content = open('app/templates/base.html', encoding='utf-8').read()

content = content.replace(
    'background: var(--g-darkest); color: rgba(255,255,255,0.85);',
    'background: #ffffff; border-bottom: 1px solid #e8ede8; color: #1e293b; box-shadow: 0 1px 4px rgba(0,0,0,0.06);'
)
content = content.replace(
    '.topbar-title { font-size: 1.05rem; font-weight: 600; color: #fff; }',
    '.topbar-title { font-size: 1.05rem; font-weight: 600; color: #1e293b; }'
)
content = content.replace(
    '.topbar-date { font-size: 0.75rem; color: rgba(255,255,255,0.5); }',
    '.topbar-date { font-size: 0.75rem; color: #94a3b8; }'
)
content = content.replace(
    '.bell-btn { background: none; border: none; color: rgba(255,255,255,0.7);',
    '.bell-btn { background: none; border: none; color: #64748b;'
)
content = content.replace(
    '.hamburger-btn { background: none; border: none; color: rgba(255,255,255,0.7);',
    '.hamburger-btn { background: none; border: none; color: #64748b;'
)

open('app/templates/base.html', 'w', encoding='utf-8').write(content)
print("Done")
