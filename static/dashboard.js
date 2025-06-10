// static/dashboard.js - Multi-Strategy Dashboard JavaScript functions with Loading Avatar (FIXED)

let currentStrategy = null;
let cooldownTimers = {}; // Store timers for each strategy

// Loading state management with avatar (FIXED)
function setButtonLoading(button, loadingText) {
    if (!button) {
        console.error('setButtonLoading: button is null');
        return;
    }
    
    // Set default loading text
    if (!loadingText) {
        loadingText = 'Loading...';
    }
    
    // Store original state
    button.dataset.originalText = button.textContent || button.innerText || '';
    button.dataset.originalHTML = button.innerHTML || '';
    
    // Create loading content with avatar (with error handling)
    try {
        const loadingHTML = '<div class="loading-content"><img src="/static/loading-avatar.png" alt="" class="loading-avatar" onerror="this.style.display=\'none\'"><span>' + loadingText + '</span></div>';
        button.innerHTML = loadingHTML;
        button.disabled = true;
        button.classList.add('loading');
    } catch (error) {
        console.error('Error setting loading state:', error);
        // Fallback to text-only loading
        button.textContent = loadingText;
        button.disabled = true;
        button.classList.add('loading');
    }
}

function restoreButton(button) {
    if (!button) {
        console.error('restoreButton: button is null');
        return;
    }
    
    try {
        const originalHTML = button.dataset.originalHTML;
        const originalText = button.dataset.originalText;
        
        if (originalHTML && originalHTML.trim() !== '') {
            button.innerHTML = originalHTML;
        } else if (originalText && originalText.trim() !== '') {
            button.textContent = originalText;
        } else {
            // Fallback text
            button.textContent = 'Button';
        }
        
        button.disabled = false;
        button.classList.remove('loading');
        
        // Clean up data attributes
        if (button.dataset.originalHTML) {
            delete button.dataset.originalHTML;
        }
        if (button.dataset.originalText) {
            delete button.dataset.originalText;
        }
    } catch (error) {
        console.error('Error restoring button state:', error);
        // Emergency fallback
        button.disabled = false;
        button.classList.remove('loading');
    }
}

// Toast notification system
function showToast(message, type) {
    if (!type) type = 'info';
    if (!message) message = 'Notification';
    
    try {
        const container = document.getElementById('toast-container');
        if (!container) {
            console.error('Toast container not found');
            return;
        }
        
        const toast = document.createElement('div');
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
    } catch (error) {
        console.error('Error showing toast:', error);
    }
}

// Tab Management
function switchToStrategy(strategyName) {
    if (!strategyName) {
        console.error('switchToStrategy: strategyName is required');
        return;
    }
    
    try {
        // Hide all strategy content
        const allContent = document.querySelectorAll('.strategy-content');
        allContent.forEach(function(content) {
            content.style.display = 'none';
        });
        
        // Remove active class from all tabs
        const allTabs = document.querySelectorAll('.tab-button:not(.tab-create)');
        allTabs.forEach(function(tab) {
            tab.classList.remove('active');
        });
        
        // Show selected strategy content
        const selectedContent = document.getElementById('strategy-' + strategyName);
        if (selectedContent) {
            selectedContent.style.display = 'block';
        }
        
        // Add active class to selected tab
        const selectedTab = document.querySelector('[data-strategy="' + strategyName + '"]');
        if (selectedTab) {
            selectedTab.classList.add('active');
        }
        
        currentStrategy = strategyName;
    } catch (error) {
        console.error('Error switching to strategy:', error);
    }
}

// Strategy Creation
function showCreateStrategy() {
    try {
        const modal = document.getElementById('create-strategy-modal');
        if (modal) {
            modal.style.display = 'flex';
        }
    } catch (error) {
        console.error('Error showing create strategy modal:', error);
    }
}

function hideCreateStrategy() {
    try {
        const modal = document.getElementById('create-strategy-modal');
        if (modal) {
            modal.style.display = 'none';
        }
        
        // Clear form
        const form = document.getElementById('create-strategy-form');
        if (form) {
            form.reset();
        }
    } catch (error) {
        console.error('Error hiding create strategy modal:', error);
    }
}

// Strategy Management Functions
function updateStrategySymbols(strategyName) {
    if (!strategyName) {
        console.error('updateStrategySymbols: strategyName is required');
        return;
    }
    
    try {
        const strategyDiv = document.getElementById('strategy-' + strategyName);
        if (!strategyDiv) {
            showToast('Strategy not found', 'error');
            return;
        }
        
        const longSymbolInput = strategyDiv.querySelector('.long-symbol-input');
        const shortSymbolInput = strategyDiv.querySelector('.short-symbol-input');
        
        const longSymbol = longSymbolInput ? longSymbolInput.value.trim() : '';
        const shortSymbol = shortSymbolInput ? shortSymbolInput.value.trim() : '';
        
        const formData = new FormData();
        formData.append('long_symbol', longSymbol);
        formData.append('short_symbol', shortSymbol);
        
        // Set loading state
        const updateButton = strategyDiv.querySelector('.symbols-form-group button');
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
                const symbolValues = strategyDiv.querySelectorAll('.symbol-value');
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
    } catch (error) {
        console.error('Error in updateStrategySymbols:', error);
        showToast('Error updating symbols', 'error');
    }
}

function updateStrategyCash(strategyName) {
    if (!strategyName) {
        console.error('updateStrategyCash: strategyName is required');
        return;
    }
    
    try {
        const strategyDiv = document.getElementById('strategy-' + strategyName);
        if (!strategyDiv) {
            showToast('Strategy not found', 'error');
            return;
        }
        
        const cashInput = strategyDiv.querySelector('.cash-amount-input');
        const cashAmount = cashInput ? cashInput.value : '';
        
        if (!cashAmount) {
            showToast('Please enter a cash amount', 'error');
            return;
        }
        
        const formData = new FormData();
        formData.append('cash_amount', cashAmount);
        
        // Set loading state
        const updateButton = strategyDiv.querySelector('.cash-section .form-group button');
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
                const cashDisplay = strategyDiv.querySelector('.cash-amount');
                if (cashDisplay) {
                    cashDisplay.textContent = '$' + result.strategy.cash_balance.toFixed(2);
                }
                
                // Clear the input field
                if (cashInput) {
                    cashInput.value = '';
                }
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
    } catch (error) {
        console.error('Error in updateStrategyCash:', error);
        showToast('Error updating cash', 'error');
    }
}

// Cooldown Management
function startStrategyCooldown(strategyName) {
    if (!strategyName) {
        console.error('startStrategyCooldown: strategyName is required');
        return;
    }
    
    try {
        // Set loading state
        const startButton = document.querySelector('#strategy-' + strategyName + ' .cooldown-controls button:first-child');
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
    } catch (error) {
        console.error('Error in startStrategyCooldown:', error);
        showToast('Error starting cooldown', 'error');
    }
}

function stopStrategyCooldown(strategyName) {
    if (!strategyName) {
        console.error('stopStrategyCooldown: strategyName is required');
        return;
    }
    
    try {
        // Set loading state
        const stopButton = document.querySelector('#strategy-' + strategyName + ' .cooldown-controls button:last-child');
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
    } catch (error) {
        console.error('Error in stopStrategyCooldown:', error);
        showToast('Error stopping cooldown', 'error');
    }
}

function updateCooldownDisplay(strategyName, cooldownData) {
    if (!strategyName || !cooldownData) {
        console.error('updateCooldownDisplay: missing parameters');
        return;
    }
    
    try {
        const strategyDiv = document.getElementById('strategy-' + strategyName);
        if (!strategyDiv) {
            console.error('Strategy div not found: ' + strategyName);
            return;
        }
        
        const statusDiv = strategyDiv.querySelector('.cooldown-active, .cooldown-inactive');
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
            const endTime = new Date(cooldownData.end_time);
            
            // Create timer element
            const timerElement = document.createElement('div');
            timerElement.className = 'cooldown-timer';
            
            // Update function for the countdown
            function updateTimer() {
                try {
                    const now = new Date();
                    const remaining = endTime - now;
                    
                    if (remaining <= 0) {
                        // Cooldown has expired
                        clearInterval(cooldownTimers[strategyName]);
                        delete cooldownTimers[strategyName];
                        updateCooldownDisplay(strategyName, { active: false });
                        return;
                    }
                    
                    const hours = Math.floor(remaining / (1000 * 60 * 60));
                    const minutes = Math.floor((remaining % (1000 * 60 * 60)) / (1000 * 60));
                    const seconds = Math.floor((remaining % (1000 * 60)) / 1000);
                    
                    timerElement.textContent = 'Time remaining: ' + hours + 'h ' + minutes + 'm ' + seconds + 's';
                } catch (error) {
                    console.error('Error updating timer:', error);
                }
            }
            
            statusDiv.innerHTML = '<div class="cooldown-label">Cooldown Active</div><div class="cooldown-end">Ends at: ' + endTime.toLocaleString() + '</div>';
            statusDiv.appendChild(timerElement);
            
            // Start the countdown timer
            updateTimer(); // Update immediately
            cooldownTimers[strategyName] = setInterval(updateTimer, 1000);
            
        } else {
            // Show inactive cooldown
            statusDiv.className = 'cooldown-inactive';
            statusDiv.innerHTML = '<div class="cooldown-label">Cooldown Inactive</div><div>Ready to process signals normally</div>';
        }
    } catch (error) {
        console.error('Error in updateCooldownDisplay:', error);
    }
}

// Helper function to get strategy symbols
function getStrategySymbols(strategyName) {
    if (!strategyName) {
        return { long: null, short: null };
    }
    
    try {
        const strategyDiv = document.getElementById('strategy-' + strategyName);
        if (!strategyDiv) {
            return { long: null, short: null };
        }
        
        const symbolValues = strategyDiv.querySelectorAll('.symbol-value');
        const longSymbol = symbolValues[0] ? symbolValues[0].textContent.trim() : 'Not set';
        const shortSymbol = symbolValues[1] ? symbolValues[1].textContent.trim() : 'Not set';
        
        return {
            long: longSymbol !== 'Not set' ? longSymbol : null,
            short: shortSymbol !== 'Not set' ? shortSymbol : null
        };
    } catch (error) {
        console.error('Error getting strategy symbols:', error);
        return { long: null, short: null };
    }
}

// Manual Trading Functions
function forceStrategyLong(strategyName) {
    if (!strategyName) {
        console.error('forceStrategyLong: strategyName is required');
        return;
    }
    
    try {
        const symbols = getStrategySymbols(strategyName);
        
        let message = 'Are you sure you want to force a LONG position for ' + strategyName + '?\n\n';
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
        
        const confirmed = confirm(message);
        
        if (!confirmed) {
            return;
        }
        
        const button = document.querySelector('#strategy-' + strategyName + ' .force-long');
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
    } catch (error) {
        console.error('Error in forceStrategyLong:', error);
        showToast('Error executing Force Long', 'error');
    }
}

function forceStrategyShort(strategyName) {
    if (!strategyName) {
        console.error('forceStrategyShort: strategyName is required');
        return;
    }
    
    try {
        const symbols = getStrategySymbols(strategyName);
        
        let message = 'Are you sure you want to force a SHORT position for ' + strategyName + '?\n\n';
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
        
        const confirmed = confirm(message);
        
        if (!confirmed) {
            return;
        }
        
        const button = document.querySelector('#strategy-' + strategyName + ' .force-short');
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
    } catch (error) {
        console.error('Error in forceStrategyShort:', error);
        showToast('Error executing Force Short', 'error');
    }
}

function forceStrategyClose(strategyName) {
    if (!strategyName) {
        console.error('forceStrategyClose: strategyName is required');
        return;
    }
    
    try {
        const symbols = getStrategySymbols(strategyName);
        
        let message = 'Are you sure you want to FORCE CLOSE ALL positions for ' + strategyName + '?\n\n';
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
        
        const confirmed = confirm(message);
        
        if (!confirmed) {
            return;
        }
        
        // Double confirmation for close all
        const doubleConfirmed = confirm(
            'FINAL CONFIRMATION:\n\n' +
            'You are about to close ALL positions for strategy "' + strategyName + '".\n\n' +
            'Are you absolutely sure?'
        );
        
        if (!doubleConfirmed) {
            return;
        }
        
        const button = document.querySelector('#strategy-' + strategyName + ' .force-close');
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
    } catch (error) {
        console.error('Error in forceStrategyClose:', error);
        showToast('Error executing Force Close', 'error');
    }
}

// Strategy Deletion
function deleteStrategy(strategyName) {
    if (!strategyName) {
        console.error('deleteStrategy: strategyName is required');
        return;
    }
    
    try {
        const confirmed = confirm(
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
        const doubleConfirmed = confirm(
            'FINAL CONFIRMATION:\n\n' +
            'Type the strategy name to confirm deletion: "' + strategyName + '"\n\n' +
            'Are you absolutely sure you want to delete this strategy?'
        );
        
        if (!doubleConfirmed) {
            return;
        }
        
        const button = document.querySelector('#strategy-' + strategyName + ' .delete-strategy-btn');
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
    } catch (error) {
        console.error('Error in deleteStrategy:', error);
        showToast('Error deleting strategy', 'error');
    }
}

// Utility Functions
function copyToClipboard(inputId) {
    if (!inputId) {
        console.error('copyToClipboard: inputId is required');
        return;
    }
    
    try {
        const input = document.getElementById(inputId);
        if (!input) {
            showToast('Element not found', 'error');
            return;
        }
        
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
    } catch (error) {
        console.error('Error copying to clipboard:', error);
        showToast('Error copying URL', 'error');
    }
}

// Event Listeners Setup
function setupEventListeners() {
    try {
        // Strategy creation form
        const createForm = document.getElementById('create-strategy-form');
        if (createForm) {
            createForm.addEventListener('submit', function(e) {
                e.preventDefault();
                
                try {
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
                    
                    // Set loading state
                    const submitButton = e.target.querySelector('button[type="submit"]');
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
                } catch (error) {
                    console.error('Error in form submission:', error);
                    showToast('Error creating strategy', 'error');
                }
            });
        }
        
        // Handle Enter key in form inputs
        document.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                const target = e.target;
                
                try {
                    // Strategy creation form
                    if (target.closest('#create-strategy-form')) {
                        e.preventDefault();
                        const submitEvent = new Event('submit');
                        createForm.dispatchEvent(submitEvent);
                        return;
                    }
                    
                    // Symbol update inputs
                    if (target.classList.contains('long-symbol-input') || target.classList.contains('short-symbol-input')) {
                        e.preventDefault();
                        const strategyDiv = target.closest('.strategy-content');
                        if (strategyDiv) {
                            const strategyName = strategyDiv.id.replace('strategy-', '');
                            updateStrategySymbols(strategyName);
                        }
                        return;
                    }
                    
                    // Cash update inputs
                    if (target.classList.contains('cash-amount-input')) {
                        e.preventDefault();
                        const strategyDiv = target.closest('.strategy-content');
                        if (strategyDiv) {
                            const strategyName = strategyDiv.id.replace('strategy-', '');
                            updateStrategyCash(strategyName);
                        }
                        return;
                    }
                } catch (error) {
                    console.error('Error handling keypress:', error);
                }
            }
        });
        
        // Close modal when clicking outside
        document.addEventListener('click', function(e) {
            try {
                const modal = document.getElementById('create-strategy-modal');
                if (e.target === modal) {
                    hideCreateStrategy();
                }
            } catch (error) {
                console.error('Error handling modal click:', error);
            }
        });
        
        // ESC key to close modal
        document.addEventListener('keydown', function(e) {
            try {
                if (e.key === 'Escape') {
                    hideCreateStrategy();
                }
            } catch (error) {
                console.error('Error handling escape key:', error);
            }
        });
        
    } catch (error) {
        console.error('Error setting up event listeners:', error);
    }
}

// Initialize cooldown timers for existing active cooldowns
function initializeCooldownTimers() {
    try {
        // Find all strategy divs and check for active cooldowns
        const strategyDivs = document.querySelectorAll('.strategy-content');
        
        strategyDivs.forEach(function(strategyDiv) {
            try {
                const strategyName = strategyDiv.id.replace('strategy-', '');
                const cooldownStatus = strategyDiv.querySelector('.cooldown-active');
                
                if (cooldownStatus) {
                    // Check if there's an end time in the DOM
                    const endTimeElement = cooldownStatus.querySelector('.cooldown-end');
                    if (endTimeElement) {
                        const endTimeText = endTimeElement.textContent;
                        const endTimeMatch = endTimeText.match(/Ends at: (.+)/);
                        
                        if (endTimeMatch) {
                            const endTime = new Date(endTimeMatch[1]);
                            // Start timer for this strategy
                            updateCooldownDisplay(strategyName, {
                                active: true,
                                end_time: endTime.toISOString()
                            });
                        }
                    }
                }
            } catch (error) {
                console.error('Error initializing cooldown timer for strategy:', error);
            }
        });
    } catch (error) {
        console.error('Error initializing cooldown timers:', error);
    }
}

// Initialize everything when page loads
document.addEventListener('DOMContentLoaded', function() {
    try {
        console.log('Dashboard JavaScript loaded');
        setupEventListeners();
        initializeCooldownTimers();
    } catch (error) {
        console.error('Error during DOMContentLoaded:', error);
    }
});
