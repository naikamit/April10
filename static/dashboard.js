// Add this function to dashboard.js after the existing functions

// Load More Logs functionality
function loadMoreLogs(strategyName) {
    if (!currentUsername) {
        showToast('Error: Username not available', 'error');
        return;
    }
    
    var loadMoreBtn = document.querySelector(`[data-strategy="${strategyName}"].load-more-btn`);
    if (!loadMoreBtn) {
        showToast('Error: Load more button not found', 'error');
        return;
    }
    
    var currentLoaded = parseInt(loadMoreBtn.getAttribute('data-loaded')) || 10;
    var logsContainer = document.getElementById(`api-logs-${strategyName}`);
    if (!logsContainer) {
        showToast('Error: Logs container not found', 'error');
        return;
    }
    
    // Set loading state
    setButtonLoading(loadMoreBtn, 'Loading...');
    
    fetch(`/api/users/${currentUsername}/strategies/${strategyName}/logs?skip=${currentLoaded}&limit=20`)
    .then(function(response) {
        return response.json();
    })
    .then(function(result) {
        if (result.status === 'success' && result.logs && result.logs.length > 0) {
            // Create HTML for new logs
            var newLogsHtml = '';
            result.logs.forEach(function(call) {
                var statusClass = '';
                var status = 'Unknown';
                if (call.response && call.response.status) {
                    status = call.response.status;
                    statusClass = status.toLowerCase();
                }
                
                newLogsHtml += `
                    <div class="api-call">
                        <div class="api-call-header">
                            <div class="timestamp-container">
                                <div class="timestamp" data-timestamp="${call.timestamp || ''}">
                                    ${call.timestamp || 'Unknown'}
                                </div>
                                <div class="timer" data-start="${call.timestamp || ''}">
                                    Calculating...
                                </div>
                            </div>
                            <div class="status ${statusClass}">
                                ${status}
                            </div>
                        </div>
                        <div class="api-call-content">
                            <div class="request">
                                <h4>Request</h4>
                                <pre>${JSON.stringify(call.request || {}, null, 2)}</pre>
                            </div>
                            <div class="response">
                                <h4>Response</h4>
                                <pre>${JSON.stringify(call.response || {}, null, 2)}</pre>
                            </div>
                        </div>
                    </div>
                `;
            });
            
            // Insert new logs before the no-api-calls div (if it exists) or at the end
            var noApiCallsDiv = logsContainer.querySelector('.no-api-calls');
            if (noApiCallsDiv) {
                noApiCallsDiv.insertAdjacentHTML('beforebegin', newLogsHtml);
            } else {
                logsContainer.insertAdjacentHTML('beforeend', newLogsHtml);
            }
            
            // Update the loaded count
            var newLoadedCount = currentLoaded + result.logs.length;
            loadMoreBtn.setAttribute('data-loaded', newLoadedCount);
            
            // Update button text and state
            if (result.pagination.has_more) {
                var remainingLogs = result.pagination.total - newLoadedCount;
                loadMoreBtn.textContent = `Load Older Logs (${remainingLogs} more)`;
            } else {
                // No more logs, hide the button
                loadMoreBtn.style.display = 'none';
            }
            
            // Update summary text
            var summaryDiv = document.querySelector(`#strategy-${strategyName} .logs-summary`);
            if (summaryDiv) {
                var totalLogs = result.pagination.total;
                var remainingLogs = totalLogs - newLoadedCount;
                summaryDiv.innerHTML = `
                    Showing ${newLoadedCount} of ${totalLogs} total logs
                    ${remainingLogs > 0 ? `(${remainingLogs} older logs available)` : ''}
                `;
            }
            
            // Initialize timers for new timestamp elements
            initializeApiTimers();
            
            showToast(`Loaded ${result.logs.length} more logs`, 'success');
            
        } else if (result.logs && result.logs.length === 0) {
            // No more logs available
            loadMoreBtn.style.display = 'none';
            showToast('No more logs available', 'info');
            
        } else {
            showToast('Error: ' + (result.detail || 'Failed to load more logs'), 'error');
        }
    })
    .catch(function(error) {
        showToast('Error loading more logs: ' + error.message, 'error');
    })
    .finally(function() {
        restoreButton(loadMoreBtn);
    });
}
