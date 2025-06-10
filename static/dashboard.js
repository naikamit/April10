// static/dashboard.js - Multi-Strategy Dashboard JavaScript functions with Loading Avatar (CORRECTED)

var currentStrategy = null;
var cooldownTimers = {}; // Store timers for each strategy

// Loading state management with avatar (CORRECTED)
function setButtonLoading(button, loadingText) {
    if (!button) return;
    
    if (!loadingText) {
        loadingText = 'Loading...';
    }
    
    button.dataset.originalText = button.textContent;
    button.dataset.originalHTML = button.innerHTML;
    
    // Create loading content with avatar (using string concatenation)
    var loadingHTML = '<div class="loading-content">' +
        '<img src="/static/loading-avatar.png" alt="" class="loading-avatar" onerror="this.style.display=\'none\'">' +
        '<span>' + loadingText + '</span>' +
        '</div>';
    
    button.innerHTML = loadingHTML;
    button.disabled = true;
    button.classList.add('loading');
}

function restoreButton(button) {
    if (!button) return;
    
    var originalHTML = button.dataset.originalHTML;
    var originalText = button.dataset.originalText;
    
    if (originalHTML) {
        button.innerHTML = originalHTML;
    } else if (originalText) {
        button.textContent = originalText;
    }
    
    button.disabled = false;
    button.classList.remove('loading');
    
    // Clean up data attributes
    delete button.dataset.originalHTML;
    delete button.dataset.originalText;
}

// Toast notification system
function showToast(message, type) {
    if (!type) type = 'info';
    
    var container = document.getElementById('toast-container');
    var toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    toast.textContent = message;
    
    container.appendChild(toast);
    
    // Trigger animation
    setTimeout(function() {
        toast.classList.add('show');
    }, 100);
    
    // Remove toast after 5 seconds
    setTimeout(function() {
        toast.classList.remove('show');
        setTimeout(function() {
            if (container.contains(toast)) {
                container.removeChild(toast);
            }
        }, 300);
    }, 5000);
}

// Tab Management
function switchToStrategy(strategyName) {
    // Hide all strategy content
    var allContent = document.querySelectorAll('.strategy-content');
    for (var i = 0; i < allContent.length; i++) {
        allContent[i].style.display = 'none';
    }
    
    // Remove active class from all tabs
    var allTabs = document.querySelectorAll('.tab-button:not(.tab-create)');
    for (var j = 0; j < allTabs.length; j++) {
        allTabs[j].classList.remove('active');
    }
    
    // Show selected strategy content
    var selectedContent = document.getElementById('strategy-' + strategyName);
    if (selectedContent) {
        selectedContent.style.display = 'block';
    }
    
    // Add active class to selected tab
    var selectedTab = document.querySelector('[data-strategy="' + strategyName + '"]');
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

// Strategy Management Functions
function updateStrategySymbols(strategyName) {
    var strategyDiv = document.getElementById('strategy-' + strategyName);
    var longSymbol = strategyDiv.querySelector('.long-symbol-input').value.trim();
    var shortSymbol = strategyDiv.querySelector('.short-symbol-input').value.trim();
    
    var formData = new FormData();
    formData.append('long_symbol', longSymbol);
    formData.append('short_symbol', shortSymbol);
    
    // Set loading state
    var updateButton = strategyDiv.querySelector('.symbols-form-group button');
    setButtonLoading(updateButton, 'Updating...');
    
    fetch('/strategies/' + strategyName + '/update-symbols', {
        method: 'POST',
        body: formData
    })
    .then(function(response) {
        return response.json();
    })
    .then(function(result) {
        if (result.status === 'success') {
            // Update the displayed symbol values
            var symbolValues = strategyDiv.querySelectorAll('.symbol-value');
            if (symbolValues[0]) {
                symbolValues[0].textContent = result.strategy.long_symbol || 'Not set';
            }
            if (symbolValues[1]) {
                symbolValues[1].textContent = result.strategy.short_symbol || 'Not set';
            }
            showToast('Symbols updated for ' + strategyName, 'success');
        } else {
            showToast('Error: ' + (result.detail || 'Failed to update symbols'), 'error');
        }
    })
    .catch(function(error) {
        showToast('Error updating symbols: ' + error.message, 'error');
    })
    .finally(function() {
        restoreButton(updateButton);
    });
}

function updateStrategyCash(strategyName) {
    var strategyDiv = document.getElementById('strategy-' + strategyName);
    var cashAmount = strategyDiv.querySelector('.cash-amount-input').value;
    
    if (!cashAmount) {
        showToast('Please enter a cash amount', 'error');
        return;
    }
    
    var formData = new FormData();
    formData.append('cash_amount', cashAmount);
    
    // Set loading state
    var updateButton = strategyDiv.querySelector('.cash-section .form-group button');
    setButtonLoading(updateButton, 'Updating...');
    
    fetch('/strategies/' + strategyName + '/update-cash', {
        method: 'POST',
        body: formData
    })
    .then(function(response) {
        return response.json();
    })
    .then(function(result) {
        if (result.status === 'success') {
            // Update the displayed cash amount
            var cashDisplay = strategyDiv.querySelector('.cash-amount');
            if (cashDisplay) {
                cashDisplay.textContent = '$' + result.strategy.cash_balance.toFixed(2);
            }
            
            // Clear the input field
            strategyDiv.querySelector('.cash-amount-input').value = '';
            showToast('Cash balance updated for ' + strategyName, 'success');
        } else {
            showToast('Error: ' + (result.detail || 'Failed to update cash balance'), 'error');
        }
    })
    .catch(function(error) {
        showToast('Error updating cash: ' + error.message, 'error');
    })
    .finally(function() {
        restoreButton(updateButton);
    });
}

// Cooldown Management
function startStrategyCooldown(strategyName) {
    // Set loading state
    var startButton = document.querySelector('#strategy-' + strategyName + ' .cooldown-controls button:first-child');
    setButtonLoading(startButton, 'Starting...');
    
    fetch('/strategies/' + strategyName + '/start-cooldown', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(function(response) {
        return response.json();
    })
    .then(function(result) {
        if (result.status === 'success' && result.strategy.cooldown.active) {
            // Update the cooldown display immediately
            updateCooldownDisplay(strategyName, result.strategy.cooldown);
            showToast('Cooldown started for ' + strategyName, 'success');
        } else {
            showToast('Error: ' + (result.detail || 'Failed to start cooldown'), 'error');
        }
    })
    .catch(function(error) {
        showToast('Error starting cooldown: ' + error.message, 'error');
    })
    .finally(function() {
        restoreButton(startButton);
    });
}

function stopStrategyCooldown(strategyName) {
    // Set loading state
    var stopButton = document.querySelector('#strategy-' + strategyName + ' .cooldown-controls button:last-child');
    setButtonLoading(stopButton, 'Stopping...');
    
    fetch('/strategies/' + strategyName + '/stop-cooldown', {
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
            // Update the cooldown display immediately
            updateCooldownDisplay(strategyName, { active: false });
            showToast('Cooldown stopped for ' + strategyName, 'success');
        } else {
            showToast('Error: ' + (result.detail || 'Failed to stop cooldown'), 'error');
        }
    })
    .catch(function(error) {
        showToast('Error stopping cooldown: ' + error.message, 'error');
    })
    .finally(function() {
        restoreButton(stopButton);
    });
}

function updateCooldownDisplay(strategyName, cooldownData) {
    var strategyDiv = document.getElementById('strategy-' + strategyName);
    if (!strategyDiv) {
        console.error('Strategy div not found: ' + strategyName);
        return;
    }
    
    var statusDiv = strategyDiv.querySelector('.cooldown-active, .cooldown-inactive');
    if (!statusDiv) {
        console.error('Cooldown status div not found for strategy: ' + strategyName);
        return;
    }
    
    // Clear existing timer for this strategy
    if (cooldownTimers[strategyName]) {
        clearInterval(cooldownTimers[strategyName]);
        delete cooldownTimers[strategyName];
    }
    
    if (cooldownData.active && cooldownData.end_time) {
        // Show active cooldown
        statusDiv.className = 'cooldown-active';
        
        // Calculate initial time remaining
        var endTime = new Date(cooldownData.end_time);
        
        // Create timer element
        var timerElement = document.createElement('div');
        timerElement.className = 'cooldown-timer';
        
        // Update function for the countdown
        function updateTimer() {
            var now = new Date();
            var remaining = endTime - now;
            
            if (remaining <= 0) {
                // Cooldown has expired
                clearInterval(cooldownTimers[strategyName]);
                delete cooldownTimers[strategyName];
                updateCooldownDisplay(strategyName, { active: false });
                return;
            }
            
            var hours = Math.floor(remaining / (1000 * 60 * 60));
            var minutes = Math.floor((remaining % (1000 * 60 * 60)) / (1000 * 60));
            var seconds = Math.floor((remaining % (1000 * 60)) / 1000);
            
            timerElement.textContent = 'Time remaining: ' + hours + 'h ' + minutes + 'm ' + seconds + 's';
        }
        
        statusDiv.innerHTML = 
            '<div class="cooldown-label">Cooldown Active</div>' +
            '<div class="cooldown-end">Ends at: ' + endTime.toLocaleString() + '</div>';
        
        statusDiv.appendChild(timerElement);
        
        // Start the countdown timer
        updateTimer(); // Update immediately
        cooldownTimers[strategyName] = setInterval(updateTimer, 1000);
        
    } else {
        // Show inactive cooldown
        statusDiv.className = 'cooldown-inactive';
        statusDiv.innerHTML = 
            '<div class="cooldown-label">Cooldown Inactive</div>' +
            '<div>Ready to process signals normally</div>';
    }
}

// Initialize cooldown timers for existing active cooldowns
function initializeCooldownTimers() {
    // Find all strategy divs and check for active cooldowns
    var strategyDivs = document.querySelectorAll('.strategy-content');
    
    for (var i = 0; i < strategyDivs.length; i++) {
        var strategyDiv = strategyDivs[i];
        var strategyName = strategyDiv.id.replace('strategy-', '');
        var cooldownStatus = strategyDiv.querySelector('.cooldown-active');
        
        if (cooldownStatus) {
            // Check if there's an end time in the DOM
            var endTimeElement = cooldownStatus.querySelector('.cooldown-end');
            if (endTimeElement) {
                var endTimeText = endTimeElement.textContent;
                var endTimeMatch = endTimeText.match(/Ends at: (.+)/);
                
                if (endTimeMatch) {
                    var endTime = new Date(endTimeMatch[1]);
                    // Start timer for this strategy
                    updateCooldownDisplay(strategyName, {
                        active: true,
                        end_time: endTime.toISOString()
                    });
                }
            }
        }
    }
}

// Helper function to get strategy symbols
function getStrategySymbols(strategyName) {
    var strategyDiv = document.getElementById('strategy-' + strategyName);
    var symbolValues = strategyDiv.querySelectorAll('.symbol-value');
    var longSymbol = symbolValues[0] ? symbolValues[0].textContent.trim() : 'Not set';
    var shortSymbol = symbolValues[1] ? symbolValues[1].textContent.trim() : 'Not set';
    
    return {
        long: longSymbol !== 'Not set' ? longSymbol : null,
        short: shortSymbol !== 'Not set' ? shortSymbol : null
    };
}

// Manual Trading Functions
function forceStrategyLong(strategyName) {
    var symbols = getStrategySymbols(strategyName);
    
    var message = 'Are you sure you want to force a LONG position for ' + strategyName + '?\n\n';
    message += 'This will:\n';
    
    if (symbols.short) {
        message += '• Close any ' + symbols.short + ' positions\n';
    } else {
        message += '• Close any short positions\n';
    }
    
    if (symbols.long) {
        message += '• Buy ' + symbols.long + '\n';
    } else {
        message += '• Buy the long symbol\n';
    }
    
    message += '• Bypass cooldown periods\n\n';
    message += 'Click OK to proceed.';
    
    var confirmed = confirm(message);
    
    if (!confirmed) {
        return;
    }
    
    var button = document.querySelector('#strategy-' + strategyName + ' .force-long');
    setButtonLoading(button, 'Processing...');
    
    fetch('/strategies/' + strategyName + '/force-long', {
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
            showToast('Force Long executed for ' + strategyName, 'success');
        } else {
            showToast('Error: ' + (result.message || 'Unknown error'), 'error');
        }
    })
    .catch(function(error) {
        showToast('Error executing Force Long: ' + error.message, 'error');
    })
    .finally(function() {
        restoreButton(button);
    });
}

function forceStrategyShort(strategyName) {
    var symbols = getStrategySymbols(strategyName);
    
    var message = 'Are you sure you want to force a SHORT position for ' + strategyName + '?\n\n';
    message += 'This will:\n';
    
    if (symbols.long) {
        message += '• Close any ' + symbols.long + ' positions\n';
    } else {
        message += '• Close any long positions\n';
    }
    
    if (symbols.short) {
        message += '• Buy ' + symbols.short + '\n';
    } else {
        message += '• Buy the short symbol\n';
    }
    
    message += '• Bypass cooldown periods\n\n';
    message += 'Click OK to proceed.';
    
    var confirmed = confirm(message);
    
    if (!confirmed) {
        return;
    }
    
    var button = document.querySelector('#strategy-' + strategyName + ' .force-short');
    setButtonLoading(button, 'Processing...');
    
    fetch('/strategies/' + strategyName + '/force-short', {
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
            showToast('Force Short executed for ' + strategyName, 'success');
        } else {
            showToast('Error: ' + (result.message || 'Unknown error'), 'error');
        }
    })
    .catch(function(error) {
        showToast('Error executing Force Short: ' + error.message, 'error');
    })
    .finally(function() {
        restoreButton(button);
    });
}

function forceStrategyClose(strategyName) {
    var symbols = getStrategySymbols(strategyName);
    
    var message = 'Are you sure you want to FORCE CLOSE ALL positions for ' + strategyName + '?\n\n';
    message += 'This will:\n';
    
    if (symbols.long) {
        message += '• Close ALL ' + symbols.long + ' positions\n';
    } else {
        message += '• Close ALL long positions\n';
    }
    
    if (symbols.short) {
        message += '• Close ALL ' + symbols.short + ' positions\n';
    } else {
        message += '• Close ALL short positions\n';
    }
    
    message += '• Bypass cooldown periods\n\n';
    message += 'This action affects BOTH symbols for this strategy!';
    
    var confirmed = confirm(message);
    
    if (!confirmed) {
        return;
    }
    
    // Double confirmation for close all
    var doubleConfirmed = confirm(
        'FINAL CONFIRMATION:\n\n' +
        'You are about to close ALL positions for strategy "' + strategyName + '".\n\n' +
        'Are you absolutely sure?'
    );
    
    if (!doubleConfirmed) {
        return;
    }
    
    var button = document.querySelector('#strategy-' + strategyName + ' .force-close');
    setButtonLoading(button, 'Processing...');
    
    fetch('/strategies/' + strategyName + '/force-close', {
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
            showToast('Force Close executed for ' + strategyName + ' - All positions closed', 'success');
        } else {
            showToast('Error: ' + (result.message || 'Unknown error'), 'error');
        }
    })
    .catch(function(error) {
        showToast('Error executing Force Close: ' + error.message, 'error');
    })
    .finally(function() {
        restoreButton(button);
    });
}

// Strategy Deletion
function deleteStrategy(strategyName) {
    var confirmed = confirm(
        'Are you sure you want to DELETE strategy "' + strategyName + '"?\n\n' +
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
    var doubleConfirmed = confirm(
        'FINAL CONFIRMATION:\n\n' +
        'Type the strategy name to confirm deletion: "' + strategyName + '"\n\n' +
        'Are you absolutely sure you want to delete this strategy?'
    );
    
    if (!doubleConfirmed) {
        return;
    }
    
    var button = document.querySelector('#strategy-' + strategyName + ' .delete-strategy-btn');
    setButtonLoading(button, 'Deleting...');
    
    fetch('/strategies/' + strategyName, {
        method: 'DELETE'
    })
    .then(function(response) {
        return response.json();
    })
    .then(function(result) {
        if (result.status === 'success') {
            showToast('Strategy "' + strategyName + '" deleted successfully', 'success');
            // Reload page to remove the deleted strategy
            setTimeout(function() {
                window.location.reload();
            }, 1000);
        } else {
            showToast('Error: ' + (result.detail || 'Failed to delete strategy'), 'error');
        }
    })
    .catch(function(error) {
        showToast('Error deleting strategy: ' + error.message, 'error');
    })
    .finally(function() {
        restoreButton(button);
    });
}

// Utility Functions
function copyToClipboard(inputId) {
    var input = document.getElementById(inputId);
    input.select();
    input.setSelectionRange(0, 99999); // For mobile devices
    
    try {
        document.execCommand('copy');
        showToast('URL copied to clipboard!', 'success');
    } catch (err) {
        // Fallback for modern browsers
        if (navigator.clipboard) {
            navigator.clipboard.writeText(input.value).then(function() {
                showToast('URL copied to clipboard!', 'success');
            }).catch(function() {
                showToast('Failed to copy URL', 'error');
            });
        } else {
            showToast('Copy not supported', 'error');
        }
    }
}

// Handle strategy creation form submission
function setupCreateStrategyForm() {
    var createForm = document.getElementById('create-strategy-form');
    if (createForm) {
        createForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            var name = document.getElementById('strategy-name').value.trim();
            var longSymbol = document.getElementById('strategy-long-symbol').value.trim();
            var shortSymbol = document.getElementById('strategy-short-symbol').value.trim();
            var cash = parseFloat(document.getElementById('strategy-cash').value) || 0;
            
            if (!name) {
                showToast('Strategy name is required', 'error');
                return;
            }
            
            // Validate strategy name
            if (!/^[a-zA-Z0-9_]{3,50}$/.test(name)) {
                showToast('Strategy name must be 3-50 characters, alphanumeric and underscores only', 'error');
                return;
            }
            
            var formData = new FormData();
            formData.append('name', name);
            if (longSymbol) formData.append('long_symbol', longSymbol);
            if (shortSymbol) formData.append('short_symbol', shortSymbol);
            formData.append('cash_balance', cash);
            
            // Set loading state
            var submitButton = e.target.querySelector('button[type="submit"]');
            setButtonLoading(submitButton, 'Creating...');
            
            fetch('/strategies', {
                method: 'POST',
                body: formData
            })
            .then(function(response) {
                return response.json();
            })
            .then(function(result) {
                if (result.status === 'success') {
                    showToast('Strategy "' + name + '" created successfully!', 'success');
                    hideCreateStrategy();
                    // Reload page to show new strategy
                    setTimeout(function() {
                        window.location.reload();
                    }, 1000);
                } else {
                    showToast('Error: ' + (result.detail || 'Failed to create strategy'), 'error');
                }
            })
            .catch(function(error) {
                showToast('Error creating strategy: ' + error.message, 'error');
            })
            .finally(function() {
                restoreButton(submitButton);
            });
        });
    }
}

// Handle Enter key in form inputs
document.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        var target = e.target;
        
        // Strategy creation form
        if (target.closest('#create-strategy-form')) {
            e.preventDefault();
            var submitEvent = new Event('submit');
            document.getElementById('create-strategy-form').dispatchEvent(submitEvent);
            return;
        }
        
        // Symbol update inputs
        if (target.classList.contains('long-symbol-input') || target.classList.contains('short-symbol-input')) {
            e.preventDefault();
            var strategyDiv = target.closest('.strategy-content');
            var strategyName = strategyDiv.id.replace('strategy-', '');
            updateStrategySymbols(strategyName);
            return;
        }
        
        // Cash update inputs
        if (target.classList.contains('cash-amount-input')) {
            e.preventDefault();
            var strategyDiv = target.closest('.strategy-content');
            var strategyName = strategyDiv.id.replace('strategy-', '');
            updateStrategyCash(strategyName);
            return;
        }
    }
});

// Close modal when clicking outside
document.addEventListener('click', function(e) {
    var modal = document.getElementById('create-strategy-modal');
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

// Initialize everything when page loads
document.addEventListener('DOMContentLoaded', function() {
    setupCreateStrategyForm();
    initializeCooldownTimers();
});
