content = open('app/templates/base.html', encoding='utf-8').read()

old = '''        .admin-topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0.85rem 2rem;
            background: var(--g-darkest);
            color: rgba(255,255,255,0.85);
            font-size: 0.82rem;
            gap: 1rem;
            position: sticky; top: 0; z-index: 100;
        }'''

new = '''        .admin-topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0.85rem 2rem;
            background: #ffffff;
            border-bottom: 1px solid #e8ede8;
            color: #1e293b;
            font-size: 0.82rem;
            gap: 1rem;
            position: sticky; top: 0; z-index: 100;
            box-shadow: 0 1px 4px rgba(0,0,0,0.06);
        }'''

result = content.replace(old, new)

# Also fix text colors inside topbar for dark-on-white
result = result.replace(
    '        .topbar-title { font-size: 1.05rem; font-weight: 600; color: #fff; }',
    '        .topbar-title { font-size: 1.05rem; font-weight: 600; color: #1e293b; }'
)
result = result.replace(
    '        .topbar-date { font-size: 0.75rem; color: rgba(255,255,255,0.5); }',
    '        .topbar-date { font-size: 0.75rem; color: #94a3b8; }'
)
result = result.replace(
    '        .bell-btn { background: none; border: none; color: rgba(255,255,255,0.7); font-size: 1.1rem; cursor: pointer; padding: 4px; }',
    '        .bell-btn { background: none; border: none; color: #94a3b8; font-size: 1.1rem; cursor: pointer; padding: 4px; }'
)
result = result.replace(
    '        .hamburger-btn { background: none; border: none; color: rgba(255,255,255,0.7); font-size: 1.1rem; cursor: pointer; padding: 2px 4px; display: none; }',
    '        .hamburger-btn { background: none; border: none; color: #94a3b8; font-size: 1.1rem; cursor: pointer; padding: 2px 4px; display: none; }'
)

if result == content:
    print("ERROR: topbar style not found - paste base.html topbar CSS")
else:
    open('app/templates/base.html', 'w', encoding='utf-8').write(result)
    print("Done")
