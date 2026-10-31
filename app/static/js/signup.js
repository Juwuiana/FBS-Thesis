        document.addEventListener('DOMContentLoaded', function() {
            // ALL VARIABLES
            const passwordInput = document.getElementById('password');
            const confirmPasswordInput = document.getElementById('confirm_password');
            const toggleBtn = document.getElementById('togglePassword');
            const toggleConfirmBtn = document.getElementById('toggleConfirmPassword');
            
            const ruleMatch = document.getElementById('rule-match');
            const strengthLabel = document.getElementById('strength-label');
            const strengthBar = document.getElementById('strength-bar-fill');
            const submitBtn = document.getElementById('signupSubmit');
            const termsBox = document.getElementById('terms');

            // keep in sync with PASSWORD_REGEX in auth_controller.py
            // Accepted: "Tr0ub4dor&3xYz!", "Blue-Horse-Battery-7!"
            // Rejected: "000000000000", "aaaaaaaaaaaa", "Password1234", "password123!", "PASSWORD123!",
            //           "Password!!!!!!", "Passw0rd!   x", "Passsword1!x1", "Short1!aBcd" (11 chars)
            const PASSWORD_PATTERN = '^(?=.*[a-z])(?=.*[A-Z])(?=.*[0-9])(?=.*[^A-Za-z0-9\\s])(?!.*(.)\\1\\1)\\S{12,128}$';
            const PASSWORD_REGEX = new RegExp(PASSWORD_PATTERN);

            const circle2 = document.getElementById('circle-2');
            const label2 = document.getElementById('label-2');
            const line1 = document.getElementById('line-1');
            const circle3 = document.getElementById('circle-3');
            const label3 = document.getElementById('label-3');
            const line2 = document.getElementById('line-2');

            const fName = document.getElementById('first_name');
            const lName = document.getElementById('last_name');
            const email = document.getElementById('email');
            const role = document.getElementById('role');
            const facility = document.getElementById('facility');
            const barangayName = document.getElementById('barangay_name');
            const barangayManual = document.getElementById('barangay_manual');
            const barangaySelect = document.getElementById('barangay_select');

            const phone = document.getElementById('phone');
            
            const modal = document.getElementById("legalModal");
            const closeBtn = document.querySelector(".close-modal");

            const legalTexts = {
                terms: {
                    title: "Terms of Use",
                    body: `<p>1. <strong>Authorized Use:</strong> This system is for LHU personnel only.</p>
                        <p>2. <strong>Account Security:</strong> You are responsible for your login credentials.</p>
                        <p>3. <strong>Data Privacy:</strong> All usage is monitored under RA 10173.</p>`
                },
                privacy: {
                    title: "Privacy Policy",
                    body: `<p>1. <strong>Collection:</strong> We collect health data for screening purposes.</p>
                        <p>2. <strong>Security:</strong> Data is stored securely on local LHU hardware.</p>
                        <p>3. <strong>Patient Rights:</strong> Patients have rights under RA 10173 to access their records.</p>`
                }
            };

            // Open Modal function
            document.querySelectorAll('.text-link').forEach(link => {
                link.addEventListener('click', function(e) {
                    e.preventDefault();
                    const type = this.getAttribute('href').replace('/', '');
                    document.getElementById('modal-title').textContent = legalTexts[type].title;
                    document.getElementById('modal-body').innerHTML = legalTexts[type].body;
                    modal.style.display = "block";
                });
            });

            // Close Modal
            closeBtn.onclick = () => modal.style.display = "none";
            window.onclick = (e) => { if (e.target == modal) modal.style.display = "none"; }
                                // TOGGLE LOGIC
            function setupToggle(inputEl, btnEl) {
                let timeoutId;
                btnEl.addEventListener('click', function() {
                    const isPassword = inputEl.getAttribute('type') === 'password';
                    inputEl.setAttribute('type', isPassword ? 'text' : 'password');
                    this.textContent = isPassword ? 'Hide' : 'Show';
                    clearTimeout(timeoutId);
                    if (isPassword) {
                        timeoutId = setTimeout(() => {
                            inputEl.setAttribute('type', 'password');
                            btnEl.textContent = 'Show';
                        }, 5000); 
                    }
                });
            }
            setupToggle(passwordInput, toggleBtn);
            setupToggle(confirmPasswordInput, toggleConfirmBtn);

            // VALIDATION FUNCTIONS
            function checkMatch() {
                const val1 = passwordInput.value;
                const val2 = confirmPasswordInput.value;
                const ok = val2.length > 0 && val1 === val2;
                ruleMatch.classList.toggle('valid', ok);
                ruleMatch.classList.toggle('invalid', !ok);
                return ok;
            }

            // Does the password contain the user's name or email local part (parts under 3 chars ignored)?
            function containsPersonalInfo(pw) {
                const lowered = pw.toLowerCase();
                const parts = [fName.value, lName.value, email.value.split('@')[0]]
                    .map(p => p.trim().toLowerCase())
                    .filter(p => p.length >= 3);
                return parts.some(p => lowered.includes(p));
            }

            function hasSequence(pw) {
                const s = pw.toLowerCase();
                const runs = ['abcdefghijklmnopqrstuvwxyz', 'zyxwvutsrqponmlkjihgfedcba', '0123456789', '9876543210', 'qwertyuiop', 'asdfghjkl', 'zxcvbnm'];
                return runs.some(run => {
                    for (let i = 0; i + 4 <= run.length; i++) {
                        if (s.includes(run.substr(i, 4))) return true;
                    }
                    return false;
                });
            }

            const RULES = [
                ['rule-length', pw => pw.length >= 12],
                ['rule-upper', pw => /[A-Z]/.test(pw)],
                ['rule-lower', pw => /[a-z]/.test(pw)],
                ['rule-number', pw => /[0-9]/.test(pw)],
                ['rule-special', pw => /[^A-Za-z0-9\s]/.test(pw)],
                ['rule-repeat', pw => !/(.)\1\1/s.test(pw) && !/\s/.test(pw)],
                ['rule-name', pw => !containsPersonalInfo(pw)],
            ];

            // Updates the checklist and strength meter; returns true when every policy rule passes.
            function evaluatePassword() {
                const pw = passwordInput.value;
                RULES.forEach(([id, test]) => {
                    const ok = pw.length > 0 && test(pw);
                    const el = document.getElementById(id);
                    el.classList.toggle('valid', ok);
                    el.classList.toggle('invalid', !ok);
                });
                const passes = PASSWORD_REGEX.test(pw) && !containsPersonalInfo(pw);

                let text, width, color;
                if (pw.length === 0) {
                    text = 'None'; width = '0%'; color = '#ef4444';
                } else if (!passes) {
                    text = 'Weak'; width = '25%'; color = '#ef4444';
                } else if (pw.length < 14) {
                    text = 'Fair'; width = '50%'; color = '#f59e0b';
                } else if (pw.length < 16 || hasSequence(pw)) {
                    text = 'Good'; width = '75%'; color = '#84cc16';
                } else {
                    text = 'Strong'; width = '100%'; color = 'var(--green-accent)';
                }
                strengthLabel.textContent = text;
                strengthLabel.style.color = color;
                strengthBar.style.width = width;
                strengthBar.style.background = color;
                return passes;
            }

            function updateSubmit() {
                submitBtn.disabled = !(evaluatePassword() && checkMatch() && termsBox.checked);
            }

            function updateProgress() {
                const phoneValid = phone.checkValidity();
                
                const section1Valid = fName.value.trim() !== '' && 
                                    lName.value.trim() !== '' && 
                                    email.checkValidity() && 
                                    phoneValid;
                                    
                const section2Valid = role.value !== '' && 
                                    facility.value !== '' && 
                                    (barangayName.value !== '' || barangaySelect.value !== '' || barangayManual.value.trim() !== '');

                if (section1Valid) {
                    line1.classList.add('active');
                    circle2.classList.add('active');
                    circle2.classList.remove('outline');
                    label2.classList.add('active');
                } else {
                    line1.classList.remove('active');
                    circle2.classList.remove('active');
                    circle2.classList.add('outline');
                    label2.classList.remove('active');
                }

                if (section1Valid && section2Valid) {
                    line2.classList.add('active');
                    circle3.classList.add('active');
                    circle3.classList.remove('outline');
                    label3.classList.add('active');
                } else {
                    line2.classList.remove('active');
                    circle3.classList.remove('active');
                    circle3.classList.add('outline');
                    label3.classList.remove('active');
                }
            }

            // EVENT LISTENERS
            passwordInput.addEventListener('input', updateSubmit);
            confirmPasswordInput.addEventListener('input', updateSubmit);
            termsBox.addEventListener('change', updateSubmit);
            [fName, lName, email].forEach(el => el.addEventListener('input', updateSubmit));
            
            document.querySelectorAll('.field-input').forEach(input => {
                input.addEventListener('input', updateProgress);
                input.addEventListener('change', updateProgress);
            });
            updateSubmit();
            updateProgress();
        });
