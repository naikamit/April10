# Add this new endpoint to main.py after the existing user-aware API endpoints

@app.get("/api/users/{username}/strategies/{strategy_name}/logs")
async def get_user_strategy_logs(username: str, strategy_name: str, skip: int = 0, limit: int = 20):
    """Get API logs for a specific user's strategy with pagination"""
    try:
        # Check if user exists
        if not user_exists(username):
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        
        strategy = strategy_repo.get_strategy_by_owner_and_name(username, strategy_name)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{strategy_name}' not found for user '{username}'")
        
        # Get all API calls for this strategy
        all_logs = getattr(strategy, 'api_calls', [])
        total_count = len(all_logs)
        
        # Apply pagination (skip from the end since we want most recent first)
        start_idx = max(0, total_count - skip - limit)
        end_idx = total_count - skip
        
        if start_idx >= end_idx:
            # No more logs to return
            paginated_logs = []
        else:
            paginated_logs = all_logs[start_idx:end_idx]
            # Reverse to show most recent first
            paginated_logs = list(reversed(paginated_logs))
        
        return {
            "status": "success",
            "logs": paginated_logs,
            "pagination": {
                "skip": skip,
                "limit": limit,
                "total": total_count,
                "returned": len(paginated_logs),
                "has_more": (skip + limit) < total_count
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"🔥 ERROR: get_user_strategy_logs error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
