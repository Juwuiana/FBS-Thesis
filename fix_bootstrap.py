content = open('app/templates/base.html', encoding='utf-8').read()

old = '    <link rel="stylesheet" href="{{ url_for(\'static\', filename=\'css/style.css\') }}">'
new = '    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">\n    <link rel="stylesheet" href="{{ url_for(\'static\', filename=\'css/style.css\') }}">'

result = content.replace(old, new)
if result == content:
    print("ERROR: not found")
else:
    open('app/templates/base.html', 'w', encoding='utf-8').write(result)
    print("Done")
