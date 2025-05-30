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
            // Update the displayed symbol values
            var symbolValues = document.querySelectorAll('.symbol-value');
            if (symbolValues[0]) {
                symbolValues[0].textContent = result.symbols.long_symbol || 'Not set';
            }
            if (symbolValues[1]) {
                symbolValues[1].textContent = result.symbols.short_symbol || 'Not set';
            }
            
            // Clear the input fields
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
            // Update the displayed cash amount
            var cashDisplay = document.querySelector('.cash-amount');
            if (cashDisplay) {
                cashDisplay.textContent = '$' + result.cash_balance.toFixed(2);
            }
            
            // Clear the input field
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
            // Update the cooldown display
            var statusDiv = document.querySelector('.cooldown-card > div:first-child');
            if (statusDiv) {
                statusDiv.className = 'cooldown-active';
                statusDiv.innerHTML = 
                    '<div class="cooldown-label">Cooldown Active</div>' +
                    '<div class="cooldown-timer">Time remaining: ' + 
                    result.cooldown.remaining.hours + 'h ' + 
                    result.cooldown.remaining.minutes + 'm</div>' +
                    '<div class="cooldown-end">Ends at: ' + 
                    new Date(result.cooldown.end_time).toLocaleString() + '</div>';
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
            // Update the cooldown display
            var statusDiv = document.querySelector('.cooldown-card > div:first-child');
            if (statusDiv) {
                statusDiv.className = 'cooldown-inactive';
                statusDiv.innerHTML = 
                    '<div class="cooldown-label">Cooldown Inactive</div>' +
                    '<div>Ready to process signals normally</div>';
            }
        }
    })
    .catch(function(error) {
        alert('Error stopping cooldown: ' + error);
    });
}

function forceLong() {
    var confirmed = confirm(
        'Are you sure you want to force a LONG position?\n\n' +
        'This will:\n' +
        '• Close any short positions\n' +
        '• Buy the long symbol\n' +
        '• Bypass cooldown periods\n\n' +
        'Click OK to proceed.'
    );
    
    if (!confirmed) {
        return;
    }
    
    var button = document.querySelector('.force-long');
    button.disabled = true;
    button.textContent = 'Processing...';
    
    fetch('/force-long', {
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
            alert('Force Long executed successfully');
        } else {
            alert('Error: ' + (result.message || 'Unknown error'));
        }
    })
    .catch(function(error) {
        alert('Error executing Force Long: ' + error);
    })
    .finally(function() {
        button.disabled = false;
        button.textContent = 'Force Long';
    });
}

function forceShort() {
    var confirmed = confirm(
        'Are you sure you want to force a SHORT position?\n\n' +
        'This will:\n' +
        '• Close any long positions\n' +
        '• Buy the short symbol\n' +
        '• Bypass cooldown periods\n\n' +
        'Click OK to proceed.'
    );
    
    if (!confirmed) {
        return;
    }
    
    var button = document.querySelector('.force-short');
    button.disabled = true;
    button.textContent = 'Processing...';
    
    fetch('/force-short', {
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
            alert('Force Short executed successfully');
        } else {
            alert('Error: ' + (result.message || 'Unknown error'));
        }
    })
    .catch(function(error) {
        alert('Error executing Force Short: ' + error);
    })
    .finally(function() {
        button.disabled = false;
        button.textContent = 'Force Short';
    });
}

function forceClose() {
    var confirmed = confirm(
        'Are you sure you want to FORCE CLOSE ALL positions?\n\n' +
        'This will:\n' +
        '• Close ALL long positions\n' +
        '• Close ALL short positions\n' +
        '• Bypass cooldown periods\n\n' +
        'This action affects BOTH symbols!'
    );
    
    if (!confirmed) {
        return;
    }
    
    // Double confirmation for close all
    var doubleConfirmed = confirm(
        'FINAL CONFIRMATION:\n\n' +
        'You are about to close ALL positions for BOTH long and short symbols.\n\n' +
        'Are you absolutely sure?'
    );
    
    if (!doubleConfirmed) {
        return;
    }
    
    var button = document.querySelector('.force-close');
    button.disabled = true;
    button.textContent = 'Processing...';
    
    fetch('/force-close', {
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
            alert('Force Close executed successfully - All positions closed');
        } else {
            alert('Error: ' + (result.message || 'Unknown error'));
        }
    })
    .catch(function(error) {
        alert('Error executing Force Close: ' + error);
    })
    .finally(function() {
        button.disabled = false;
        button.textContent = 'Force Close';
    });
}
