content = open('app/templates/dashboard/index.html', encoding='utf-8').read()

old = '{% block content %}\n<main class="page-content">'
new = '''{% block content %}
<div style="margin-bottom:1.5rem;">
  <div style="font-size:12px;color:#94a3b8;">Santa Rosa City Health Office — Diabetes Risk Overview</div>
</div>'''

result = content.replace(old, new)

# Also fix closing tag
result = result.replace('\n</main>\n{% endblock %}', '\n{% endblock %}')

if result == content:
    print("ERROR: not found")
else:
    open('app/templates/dashboard/index.html', 'w', encoding='utf-8').write(result)
    print("Done")
