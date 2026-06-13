content = open('app/static/js/main.js', encoding='utf-8').read()

old = 'Chart.defaults.responsive = true;\nChart.defaults.maintainAspectRatio = true;'
new = 'Chart.defaults.responsive = true;\nChart.defaults.maintainAspectRatio = false;'

result = content.replace(old, new)
if result == content:
    print("ERROR: not found")
else:
    open('app/static/js/main.js', 'w', encoding='utf-8').write(result)
    print("Done")
