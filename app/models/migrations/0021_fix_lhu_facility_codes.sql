-- Replace the historical RHU facility codes with the canonical LHU codes.
UPDATE users SET facility = 'lhui' WHERE facility = 'rhui';
UPDATE users SET facility = 'lhuii' WHERE facility = 'rhuii';