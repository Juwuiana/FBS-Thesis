content = open('app/templates/nurse/nurse_data_management.html', encoding='utf-8').read()

old = '                <tbody>\n                    <tr>\n                        <td>CAB-2025-0156</td>\n                        <td>Juan Dela Cruz</td>\n                        <td>30</td>\n                        <td>M</td>\n                        <td>142</td>\n                        <td><span class="risk-badge badge-danger">High</span></td>\n                        <td>May 27, 2025</td>\n                        <td>\n                            <a href="#" class="btn btn-secondary" style="padding:0.35rem 0.75rem; font-size:0.75rem;">View</a>\n                        </td>\n                    </tr>\n                </tbody>'

new = '''                <tbody>
                    {% for p in patients %}
                    <tr>
                        <td style="font-size:0.8rem;">{{ p.id }}</td>
                        <td style="font-weight:600;">{{ p.name }}</td>
                        <td>{{ p.age }}</td>
                        <td>{{ p.sex }}</td>
                        <td style="font-weight:700;">{{ p.fbs }}</td>
                        <td>
                            {% if p.risk == "High" %}
                                <span class="risk-badge badge-danger">High</span>
                            {% elif p.risk == "Moderate" %}
                                <span class="risk-badge badge-warning">Moderate</span>
                            {% else %}
                                <span class="risk-badge badge-success">Low</span>
                            {% endif %}
                        </td>
                        <td style="font-size:0.85rem;">{{ p.date }}</td>
                        <td>
                            <a href="#" class="btn btn-secondary" style="padding:0.35rem 0.75rem; font-size:0.75rem;">View</a>
                        </td>
                    </tr>
                    {% else %}
                    <tr><td colspan="8" style="text-align:center; padding:2rem;">No records found.</td></tr>
                    {% endfor %}
                </tbody>'''

result = content.replace(old, new)
if result == content:
    print('ERROR: old string not found - no changes made')
else:
    open('app/templates/nurse/nurse_data_management.html', 'w', encoding='utf-8').write(result)
    print('Done - table updated')
