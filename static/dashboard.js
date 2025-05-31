// static/dashboard.js - Multi-Strategy Dashboard JavaScript functions

let currentStrategy = null;

// Toast notification system
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    
    container.appendChild(toast);
    
    // Trigger animation
    setTimeout(() => toast.classList.add('show'), 100);
    
    // Remove toast after 5 seconds
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => container.removeChild(toast), 300);
    }, 5000);
}

// Tab Management
function switchToStrategy(strategyName) {
    // Hide all strategy content
    const allContent = document.querySelectorAll('.strategy-content');
    allContent.forEach(content => content.style.display = 'none');
    
    // Remove active class from all tabs
    const allTabs = document.querySelectorAll('.tab-button:not(.tab-create)');
    allTabs.forEach(tab => tab.classList.remove('active'));
    
    // Show selected strategy content
    const selectedContent = document.getElementById(`strategy-${strategyName}`);
    if (selectedContent) {
        selectedContent.style.display = 'block';
    }
    
    // Add active class to selected tab
    const selectedTab = document.querySelector(`[data-strategy="${strategyName}"]`);
    if (selectedTab) {
        selectedTab.classList.add('active');
    }
    
    currentStrategy = strategyName;
}

// Strategy Creation
function showCreateStrategy() {
    document.getElementById('create-strategy-modal').style.display = 'flex';
}

function hideCreateStrategy() {
    document.getElementById('create-strategy-modal').style.display = 'none';
    // Clear form
    document.getElementById('create-strategy-form').reset();
}

// Handle strategy creation form submission
document.getElementById('create-strategy-form').addEventListener('submit', function(e) {
    e.preventDefault();
    
    const name = document.getElementById('strategy-name').value.trim();
    const longSymbol = document.getElementById('strategy-long-symbol').value.trim();
    const shortSymbol = document.getElementById('strategy-short-symbol').value.trim();
    const cash = parseFloat(document.getElementById('strategy-cash').value) || 0;
    
    if (!name) {
        showToast('Strategy name is required', 'error');
        return;
    }
    
    // Validate strategy name
    if (!/^[a-zA-Z0-9_]{3,50}$/.test(name)) {
        showToast('Strategy name must be 3-50 characters, alphanumeric and underscores only', 'error');
        return;
    }
    
    const formData = new FormData();
    formData.append('name', name);
    if (longSymbol) formData.append('long_symbol', longSymbol);
    if (shortSymbol) formData.append('short_symbol', shortSymbol);
    formData.append('cash_balance', cash);
    
    // Disable form during submission
    const submitButton = e.target.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    submitButton.textContent = 'Creating...';
    
    fetch('/strategies', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(result => {
        if (result.status === 'success') {
            showToast(`Strategy "${name}" created successfully!`, 'success');
            hideCreateStrategy();
            // Reload page to show new strategy
            setTimeout(() => window.location.reload(), 1000);
        } else {
            showToast(`Error: ${result.detail || 'Failed to create strategy'}`, 'error');
        }
    })
    .catch(error => {
        showToast(`Error creating strategy: ${error.message}`, 'error');
    })
    .finally(() => {
        submitButton.disabled = false;
        submitButton.textContent = 'Create Strategy';
    });
});

// Strategy Management Functions
function updateStrategySymbols(strategyName) {
    const strategyDiv = document.getElementById(`strategy-${strategyName}`);
    const longSymbol = strategyDiv.querySelector('.long-symbol-input').value.trim();
    const shortSymbol = strategyDiv.querySelector('.short-symbol-input').value.trim();
    
    const formData = new FormData();
    formData.append('long_symbol', longSymbol);
    formData.append('short_symbol', shortSymbol);
    
    fetch(`/strategies/${strategyName}/update-symbols`, {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(result => {
        if (result.status === 'success') {
            // Update the displayed symbol values
            const symbolValues = strategyDiv.querySelectorAll('.symbol-value');
            if (symbolValues[0]) {
                symbolValues[0].textContent = result.strategy.long_symbol || 'Not set';
            }
            if (symbolValues[1]) {
                symbolValues[1].textContent = result.strategy.short_symbol || 'Not set';
            }
            showToast(`Symbols updated for ${strategyName}`, 'success');
        } else {
            showToast(`Error: ${result.detail || 'Failed to update symbols'}`, 'error');
        }
    })
    .catch(error => {
        showToast(`Error updating symbols: ${error.message}`, 'error');
    });
}

function updateStrategyCash(strategyName) {
    const strategyDiv = document.getElementById(`strategy-${strategyName}`);
    const cashAmount = strategyDiv.querySelector('.cash-amount-input').value;
    
    if (!cashAmount) {
        showToast('Please enter a cash amount', 'error');
        return;
    }
    
    const formData = new FormData();
    formData.append('cash_amount', cashAmount);
    
    fetch(`/strategies/${strategyName}/update-cash`, {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(result => {
        if (result.status === 'success') {
            // Update the displayed cash amount
            const cashDisplay = strategyDiv.querySelector('.cash-amount');
            if (cashDisplay) {
                cashDisplay.textContent = '$' + result.strategy.cash_balance.toFixed(2);
            }
            
            // Clear the input field
            strategyDiv.querySelector('.cash-amount-input').value = '';
            showToast(`Cash balance updated for ${strategyName}`, 'success');
        } else {
            showToast(`Error: ${result.detail || 'Failed to update cash balance'}`, 'error');
        }
    })
    .catch(error => {
        showToast(`Error updating cash: ${error.message}`, 'error');
    });
}

// Cooldown Management
function startStrategyCooldown(strategyName) {
    fetch(`/strategies/${strategyName}/start-cooldown`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(result => {
        if (result.status === 'success' && result.strategy.cooldown.active) {
            // Update the cooldown display
            const strategyDiv = document.getElementById(`strategy-${strategyName}`);
            const statusDiv = strategyDiv.querySelector('.cooldown-card > div:first-child');
            if (statusDiv) {
                statusDiv.className = 'cooldown-active';
                statusDiv.innerHTML = 
                    '<div class="cooldown-label">Cooldown Active</div>' +
                    '<div class="cooldown-timer">Time remaining: ' + 
                    result.strategy.cooldown.remaining.hours + 'h ' + 
                    result.strategy.cooldown.remaining.minutes + 'm</div>' +
                    '<div class="cooldown-end">Ends at: ' + 
                    new Date(result.strategy.cooldown.end_time).toLocaleString() + '</div>';
            }
            showToast(`Cooldown started for ${strategyName}`, 'success');
        } else {
            showToast(`Error: ${result.detail || 'Failed to start cooldown'}`, 'error');
        }
    })
    .catch(error => {
        showToast(`Error starting cooldown: ${error.message}`, 'error');
    });
}

function stopStrategyCooldown(strategyName) {
    fetch(`/strategies/${strategyName}/stop-cooldown`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(result => {
        if (result.status === 'success') {
            // Update the cooldown display
            const strategyDiv = document.getElementById(`strategy-${strategyName}`);
            const statusDiv = strategyDiv.querySelector('.cooldown-card > div:first-child');
            if (statusDiv) {
                statusDiv.className = 'cooldown-inactive';
                statusDiv.innerHTML = 
                    '<div class="cooldown-label">Cooldown Inactive</div>' +
                    '<div>Ready to process signals normally</div>';
            }
            showToast(`Cooldown stopped for ${strategyName}`, 'success');
        } else {
            showToast(`Error: ${result.detail || 'Failed to stop cooldown'}`, 'error');
        }
    })
    .catch(error => {
        showToast(`Error stopping cooldown: ${error.message}`, 'error');
    });
}

// Manual Trading Functions
function forceStrategyLong(strategyName) {
    const confirmed = confirm(
        `Are you sure you want to force a LONG position for ${strategyName}?\n\n` +
        'This will:\n' +
        '• Close any short positions\n' +
        '• Buy the long symbol\n' +
        '• Bypass cooldown periods\n\n' +
        'Click OK to proceed.'
    );
    
    if (!confirmed) {
        return;
    }
    
    const button = document.querySelector(`#strategy-${strategyName} .force-long`);
    button.disabled = true;
    button.textContent = 'Processing...';
    
    fetch(`/strategies/${strategyName}/force-long`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(result => {
        if (result.status === 'success') {
            showToast(`Force Long executed for ${strategyName}`, 'success');
        } else {
            showToast(`Error: ${result.message || 'Unknown error'}`, 'error');
        }
    })
    .catch(error => {
        showToast(`Error executing Force Long: ${error.message}`, 'error');
    })
    .finally(() => {
        button.disabled = false;
        button.textContent = 'Force Long';
    });
}

function forceStrategyShort(strategyName) {
    const confirmed = confirm(
        `Are you sure you want to force a SHORT position for ${strategyName}?\n\n` +
        'This will:\n' +
        '• Close any long positions\n' +
        '• Buy the short symbol\n' +
        '• Bypass cooldown periods\n\n' +
        'Click OK to proceed.'
    );
    
    if (!confirmed) {
        return;
    }
    
    const button = document.querySelector(`#strategy-${strategyName} .force-short`);
    button.disabled = true;
    button.textContent = 'Processing...';
    
    fetch(`/strategies/${strategyName}/force-short`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(result => {
        if (result.status === 'success') {
            showToast(`Force Short executed for ${strategyName}`, 'success');
        } else {
            showToast(`Error: ${result.message || 'Unknown error'}`, 'error');
        }
    })
    .catch(error => {
        showToast(`Error executing Force Short: ${error.message}`, 'error');
    })
    .finally(() => {
        button.disabled = false;
        button.textContent = 'Force Short';
    });
}

function forceStrategyClose(strategyName) {
    const confirmed = confirm(
        `Are you sure you want to FORCE CLOSE ALL positions for ${strategyName}?\n\n` +
        'This will:\n' +
        '• Close ALL long positions\n' +
        '• Close ALL short positions\n' +
        '• Bypass cooldown periods\n\n' +
        'This action affects BOTH symbols for this strategy!'
    );
    
    if (!confirmed) {
        return;
    }
    
    // Double confirmation for close all
    const doubleConfirmed = confirm(
        'FINAL CONFIRMATION:\n\n' +
        `You are about to close ALL positions for strategy "${strategyName}".\n\n` +
        'Are you absolutely sure?'
    );
    
    if (!doubleConfirmed) {
        return;
    }
    
    const button = document.querySelector(`#strategy-${strategyName} .force-close`);
    button.disabled = true;
    button.textContent = 'Processing...';
    
    fetch(`/strategies/${strategyName}/force-close`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(result => {
        if (result.status === 'success') {
            showToast(`Force Close executed for ${strategyName} - All positions closed`, 'success');
        } else {
            showToast(`Error: ${result.message || 'Unknown error'}`, 'error');
        }
    })
    .catch(error => {
        showToast(`Error executing Force Close: ${error.message}`, 'error');
    })
    .finally(() => {
        button.disabled = false;
        button.textContent = 'Force Close';
    });
}

// Strategy Deletion
function deleteStrategy(strategyName) {
    const confirmed = confirm(
        `Are you sure you want to DELETE strategy "${strategyName}"?\n\n` +
        'This will permanently remove:\n' +
        '• All strategy configuration\n' +
        '• Cash balance information\n' +
        '• API call history\n' +
        '• Webhook URLs will stop working\n\n' +
        'This action CANNOT be undone!'
    );
    
    if (!confirmed) {
        return;
    }
    
    // Double confirmation for deletion
    const doubleConfirmed = confirm(
        'FINAL CONFIRMATION:\n\n' +
        `Type the strategy name to confirm deletion: "${strategyName}"\n\n` +
        'Are you absolutely sure you want to delete this strategy?'
    );
    
    if (!doubleConfirmed) {
        return;
    }
    
    fetch(`/strategies/${strategyName}`, {
        method: 'DELETE'
    })
    .then(response => response.json())
    .then(result => {
        if (result.status === 'success') {
            showToast(`Strategy "${strategyName}" deleted successfully`, 'success');
            // Reload page to remove the deleted strategy
            setTimeout(() => window.location.reload(), 1000);
        } else {
            showToast(`Error: ${result.detail || 'Failed to delete strategy'}`, 'error');
        }
    })
    .catch(error => {
        showToast(`Error deleting strategy: ${error.message}`, 'error');
    });
}

// Utility Functions
function copyToClipboard(inputId) {
    const input = document.getElementById(inputId);
    input.select();
    input.setSelectionRange(0, 99999); // For mobile devices
    
    try {
        document.execCommand('copy');
        showToast('URL copied to clipboard!', 'success');
    } catch (err) {
        // Fallback for modern browsers
        navigator.clipboard.writeText(input.value).then(() => {
            showToast('URL copied to clipboard!', 'success');
        }).catch(() => {
            showToast('Failed to copy URL', 'error');
        });
    }
}

// Handle Enter key in form inputs
document.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        const target = e.target;
        
        // Strategy creation form
        if (target.closest('#create-strategy-form')) {
            e.preventDefault();
            document.getElementById('create-strategy-form').dispatchEvent(new Event('submit'));
            return;
        }
        
        // Symbol update inputs
        if (target.classList.contains('long-symbol-input') || target.classList.contains('short-symbol-input')) {
            e.preventDefault();
            const strategyDiv = target.closest('.strategy-content');
            const strategyName = strategyDiv.id.replace('strategy-', '');
            updateStrategySymbols(strategyName);
            return;
        }
        
        // Cash update inputs
        if (target.classList.contains('cash-amount-input')) {
            e.preventDefault();
            const strategyDiv = target.closest('.strategy-content');
            const strategyName = strategyDiv.id.replace('strategy-', '');
            updateStrategyCash(strategyName);
            return;
        }
    }
});

// Close modal when clicking outside
document.addEventListener('click', function(e) {
    const modal = document.getElementById('create-strategy-modal');
    if (e.target === modal) {
        hideCreateStrategy();
    }
});

// ESC key to close modal
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        hideCreateStrategy();
    }
});
