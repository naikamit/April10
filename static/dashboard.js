// static/dashboard.js - Dashboard JavaScript functions

function updateSymbols() {
    var longSymbol = document.getElementById('long_symbol').value;
    var shortSymbol = document.getElementById('short_symbol').value;
    
    var formData = new FormData();
    formData.append('long_symbol', longSymbol);
    formData.append('short_symbol', shortSymbol);
    
    fetch('/update-symbols', {
        method: 'POST',
        body: formData
    })
    .then(function(response) {
        return response.json();
    })
    .then(function(result) {
        if (result.status === 'success') {
            var symbolValues = document.querySelectorAll('.symbol-value');
            if (symbolValues[0]) symbolValues[0].textContent = result.symbols.long_symbol || 'Not set';
            if (symbolValues[1]) symbolValues[1].textContent = result.symbols.short_symbol || 'Not set';
            
            document.getElementById('long_symbol').value = '';
            document.getElementById('short_symbol').value = '';
        }
    })
    .catch(function(error) {
        alert('Error updating symbols: ' + error);
    });
}

function updateCash() {
    var cashAmount = document.getElementById('cash_amount').value;
    if (!cashAmount) {
        alert('Please enter a cash amount');
        return;
    }
    
    var formData = new FormData();
    formData.append('cash_amount', cashAmount);
    
    fetch('/update-cash', {
        method: 'POST',
        body: formData
    })
    .then(function(response) {
        return response.json();
    })
    .then(function(result) {
        if (result.status === 'success') {
            var cashDisplay = document.querySelector('.cash-amount');
            if (cashDisplay) cashDisplay.textContent = '$' + result.cash_balance.toFixed(2);
            
            document.getElementById('cash_amount').value = '';
        }
    })
    .catch(function(error) {
        alert('Error updating cash: ' + error);
    });
}

function startCooldown() {
    fetch('/start-cooldown', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(function(response) {
        return response.json();
    })
    .then(function(result) {
        if (result.status === 'success' && result.cooldown.active) {
            var statusDiv = document.querySelector('.cooldown-card > div:first-child');
            if (statusDiv) {
                statusDiv.className = 'cooldown-active';
                statusDiv.innerHTML = '<div class="cooldown-label">Cooldown Active</div><div class="cooldown-timer">Time remaining: ' + result.cooldown.remaining.hours + 'h ' + result.cooldown.remaining.minutes + 'm</div>';
            }
        }
    })
    .catch(function(error) {
        alert('Error starting cooldown: ' + error);
    });
}

function stopCooldown() {
    fetch('/stop-cooldown', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(function(response) {
        return response.json();
    })
    .then(function(result) {
        if (result.status === 'success') {
            var statusDiv = document.querySelector('.cooldown-card > div:first-child');
            if (statusDiv) {
                statusDiv.className = 'cooldown-inactive';
                statusDiv.innerHTML = '<div class="cooldown-label">Cooldown Inactive</div><div>Ready to process signals normally</div>';
            }
        }
    })
    .catch(function(error) {
        alert('Error stopping cooldown: ' + error);
    });
}
