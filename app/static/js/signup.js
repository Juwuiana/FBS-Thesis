        document.addEventListener('DOMContentLoaded', function() {
            // ALL VARIABLES
            const passwordInput = document.getElementById('password');
            const confirmPasswordInput = document.getElementById('confirm_password');
            const toggleBtn = document.getElementById('togglePassword');
            const toggleConfirmBtn = document.getElementById('toggleConfirmPassword');
            
            const ruleLength = document.getElementById('rule-length');
            const ruleMatch = document.getElementById('rule-match');
            const strengthLabel = document.getElementById('strength-label');
            const strengthBar = document.getElementById('strength-bar-fill');

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
            const barangay = document.getElementById('barangay');

            const phone = document.getElementById('phone');
            const phoneValid = phone.checkValidity(); 

            const section1Valid = fName.value.trim() !== '' && 
                                lName.value.trim() !== '' && 
                                email.checkValidity() &&
                                phoneValid;
            
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
                if (val2.length > 0 && val1 === val2) {
                    ruleMatch.classList.add('valid');
                    ruleMatch.classList.remove('invalid');
                } else {
                    ruleMatch.classList.remove('valid');
                    ruleMatch.classList.add('invalid');
                }
            }

            function updateProgress() {
                const phoneValid = phone.checkValidity();
                
                const section1Valid = fName.value.trim() !== '' && 
                                    lName.value.trim() !== '' && 
                                    email.checkValidity() && 
                                    phoneValid;
                                    
                const section2Valid = role.value !== '' && 
                                    facility.value !== '' && 
                                    barangay.value !== '';

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
            passwordInput.addEventListener('input', function() {
                const val = this.value;
                ruleLength.className = val.length >= 12 ? 'valid' : 'invalid';
                
                if (val.length === 0) {
                    strengthLabel.textContent = "None";
                    strengthBar.style.width = "0%";
                } else if (val.length < 12) {
                    strengthLabel.textContent = "Weak";
                    strengthBar.style.width = "25%"; strengthBar.style.background = "#ef4444";
                } else if (val.length < 16) {
                    strengthLabel.textContent = "Good";
                    strengthBar.style.width = "65%"; strengthBar.style.background = "#f59e0b";
                } else {
                    strengthLabel.textContent = "Strong";
                    strengthBar.style.width = "100%"; strengthBar.style.background = "var(--green-accent)";
                }
                checkMatch();
            });

            confirmPasswordInput.addEventListener('input', checkMatch);
            
            document.querySelectorAll('.field-input').forEach(input => {
                input.addEventListener('input', updateProgress);
                input.addEventListener('change', updateProgress);
            });
        });
