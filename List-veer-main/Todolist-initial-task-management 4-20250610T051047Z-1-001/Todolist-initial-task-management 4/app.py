from flask import Flask, render_template, redirect, url_for, request, jsonify, session, flash
import json
import os
from datetime import datetime, date, timedelta, timezone # Ensure all are imported
import uuid

app = Flask(__name__)
app.secret_key = 'dev_secret_key_123!'
ADMIN_PASSWORD = "admin123"

users = ["Veer", "Vardaan", "Avni", "Drishti"]
DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")

TAB_THEME_COLORS = {
    "Home": "#4a90e2",      # Blue
    "Dashboard": "#417505", # Green
    "Settings": "#777777",  # Grey
    "Default": "#d0d0d0"
}

IST = timezone(timedelta(hours=5, minutes=30))

# Global variable to track the last run date of the daily update
LAST_DAILY_UPDATE_RUN_DATE = None

# --- Helper Functions ---
def get_user_tasks(username):
    task_file = os.path.join(DATA_DIR, f"{username.lower()}_tasks.json")
    try:
        with open(task_file, 'r') as f:
            tasks = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        tasks = []
    return tasks

def save_user_tasks(username, tasks):
    task_file = os.path.join(DATA_DIR, f"{username.lower()}_tasks.json")
    with open(task_file, 'w') as f:
        json.dump(tasks, f, indent=4)

def get_all_user_data():
    try:
        with open(USERS_FILE, 'r') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {user: {"stars": 0, "star_history": []} for user in users}
        save_all_user_data(data)
        return data

    updated = False
    for user_name_loop in users:
        if user_name_loop not in data:
            data[user_name_loop] = {"stars": 0, "star_history": []}
            updated = True
        else:
            if "stars" not in data[user_name_loop]:
                data[user_name_loop]["stars"] = 0
                updated = True
            if "star_history" not in data[user_name_loop]:
                data[user_name_loop]["star_history"] = []
                updated = True
    if updated:
        save_all_user_data(data)
    return data

def save_all_user_data(data):
    with open(USERS_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def update_tasks_done_yesterday_logic():
    today_utc = datetime.now(timezone.utc).date()
    yesterday_utc = today_utc - timedelta(days=1)
    tasks_updated_count = 0
    for username_val in users:
        user_tasks = get_user_tasks(username_val)
        user_tasks_changed = False
        for task in user_tasks:
            if task.get('status') == 'completed' and task.get('completed_at'):
                try:
                    completed_dt = datetime.fromisoformat(task['completed_at'].replace('Z', '+00:00'))
                    completed_date_utc = completed_dt.astimezone(timezone.utc).date()
                    if completed_date_utc == yesterday_utc:
                        task['status'] = 'done_yesterday'
                        user_tasks_changed = True
                        tasks_updated_count +=1
                except ValueError as e:
                    print(f"Warning: Malformed completed_at for task {task.get('id')} for user {username_val}. Error: {e}. Value: {task.get('completed_at')}")
                    continue
            if user_tasks_changed:
                save_user_tasks(username_val, user_tasks)
    return tasks_updated_count

def get_completed_on_date_ist(user_tasks, target_date_ist):
    count = 0
    for task in user_tasks:
        if task.get('status') in ['completed', 'done_yesterday'] and task.get('completed_at'):
            try:
                completed_dt_utc = datetime.fromisoformat(task['completed_at'].replace('Z', '+00:00'))
                completed_dt_ist = completed_dt_utc.astimezone(IST)
                if completed_dt_ist.date() == target_date_ist:
                    count += 1
            except ValueError:
                continue
    return count

def get_pending_tasks_on_date_ist(user_tasks, target_date_ist):
    pending_count = 0
    for task in user_tasks:
        try:
            created_dt_utc = datetime.fromisoformat(task['created_at'].replace('Z', '+00:00'))
            created_dt_ist = created_dt_utc.astimezone(IST)

            if created_dt_ist.date() <= target_date_ist:
                is_completed_on_or_before_target = False
                if task.get('completed_at'):
                    completed_dt_utc_task = datetime.fromisoformat(task['completed_at'].replace('Z', '+00:00'))
                    completed_dt_ist_task = completed_dt_utc_task.astimezone(IST)
                    if completed_dt_ist_task.date() <= target_date_ist:
                        is_completed_on_or_before_target = True

                if not is_completed_on_or_before_target:
                    pending_count += 1
        except ValueError:
            print(f"Warning: Malformed created_at or completed_at for task {task.get('id')}. Skipping for pending count on date {target_date_ist}.")
            continue
    return pending_count

def get_tasks_completed_this_week_ist(user_tasks, start_of_week_ist, today_ist):
    count = 0
    end_of_today_ist = today_ist
    for task in user_tasks:
        if task.get('status') in ['completed', 'done_yesterday'] and task.get('completed_at'):
            try:
                completed_dt_utc = datetime.fromisoformat(task['completed_at'].replace('Z', '+00:00'))
                completed_dt_ist = completed_dt_utc.astimezone(IST)
                if start_of_week_ist <= completed_dt_ist.date() <= end_of_today_ist:
                    count += 1
            except ValueError:
                continue
    return count

@app.before_request
def run_daily_updates_if_needed():
    global LAST_DAILY_UPDATE_RUN_DATE
    # It's important to use a consistent timezone for checking the date.
    # Since update_tasks_done_yesterday_logic uses UTC for its primary date logic,
    # we should probably use UTC date here for consistency of "day".
    # Or, use IST date if we want the trigger to be based on IST midnight.
    # Let's use IST date for the trigger, as the app is IST-centric for users.
    today_ist_date = datetime.now(IST).date()

    if LAST_DAILY_UPDATE_RUN_DATE != today_ist_date:
        print(f"Running daily 'done_yesterday' update. Previous run: {LAST_DAILY_UPDATE_RUN_DATE}, Today (IST): {today_ist_date}")
        try:
            tasks_updated_count = update_tasks_done_yesterday_logic()
            LAST_DAILY_UPDATE_RUN_DATE = today_ist_date
            print(f"Daily update complete. {tasks_updated_count} tasks moved to 'done_yesterday'. Last run date set to: {LAST_DAILY_UPDATE_RUN_DATE}")
        except Exception as e:
            print(f"Error during automatic daily update: {e}")
            # Optionally, you could prevent setting LAST_DAILY_UPDATE_RUN_DATE if it fails,
            # so it tries again on the next request. For now, we'll set it to avoid constant retries on errors.
            # However, for robustness, error handling here could be more sophisticated.
            # If the error is critical, maybe don't update the date to retry.
            # If it's a minor task-specific error, updating the date might be okay.
            # The current update_tasks_done_yesterday_logic has some internal error handling (prints warnings).
            LAST_DAILY_UPDATE_RUN_DATE = today_ist_date # Still update to prevent spamming logs if one task is problematic
            print(f"Daily update attempted, but an error occurred. Last run date set to: {LAST_DAILY_UPDATE_RUN_DATE} to prevent immediate retry.")


# --- Routes ---
@app.route('/')
def index():
    home_dashboard_data = {}
    user_data_global = get_all_user_data()

    today_ist = datetime.now(IST).date()
    yesterday_ist = today_ist - timedelta(days=1)

    for user_name in users:
        user_tasks = get_user_tasks(user_name)

        # Current pending count for the main summary cards
        current_total_pending_count = 0
        for task in user_tasks:
            if task.get('status') == 'pending':
                 current_total_pending_count +=1

        completed_today_count = get_completed_on_date_ist(user_tasks, today_ist)
        completed_yesterday_count = get_completed_on_date_ist(user_tasks, yesterday_ist)

        home_dashboard_data[user_name] = {
            "stars": user_data_global.get(user_name, {}).get("stars", 0),
            "pending_count": current_total_pending_count, # Use the specifically calculated total pending
            "completed_today": completed_today_count,
            "completed_yesterday": completed_yesterday_count
        }

    return render_template("index.html",
                           home_dashboard_data=home_dashboard_data,
                           users=users,
                           active_tab="Home",
                           tab_theme_colors=TAB_THEME_COLORS,
                           current_date_str=today_ist.strftime('%A, %B %d, %Y'),
                           admin_mode=session.get('is_admin_mode', False))

@app.route('/task_view')
def main_app_view():
    requested_user_param = request.args.get('user')
    target_users_to_load = []
    display_single_user = None

    if requested_user_param and requested_user_param in users:
        target_users_to_load.append(requested_user_param)
        display_single_user = requested_user_param
    else:
        target_users_to_load.extend(users)

    all_users_display_data = {}
    user_data_global = get_all_user_data()

    for user_name in target_users_to_load:
        tasks = get_user_tasks(user_name)
        all_users_display_data[user_name] = {
            "tasks": tasks,
            "stars": user_data_global.get(user_name, {}).get("stars", 0)
        }

    return render_template("task_view.html",
                           all_users_data=all_users_display_data,
                           users=users,
                           display_user=display_single_user,
                           active_tab="Tasks",
                           tab_theme_colors=TAB_THEME_COLORS,
                           admin_mode = session.get('is_admin_mode', False))

@app.route('/admin_login', methods=['POST'])
def admin_login_global():
    password = request.form.get('admin_password')
    if password == ADMIN_PASSWORD:
        session['is_admin_mode'] = True
        flash('Admin mode activated.', 'success')
    else:
        session.pop('is_admin_mode', None)
        flash('Incorrect admin password.', 'error')
    return redirect(request.referrer or url_for('main_app_view'))

@app.route('/admin_logout', methods=['POST'])
def admin_logout_global():
    session.pop('is_admin_mode', None)
    flash('Admin mode deactivated.', 'info')
    return redirect(request.referrer or url_for('main_app_view'))

@app.route('/add_user_admin', methods=['POST'])
def add_user_admin():
    if not session.get('is_admin_mode', False):
        flash('Admin access required to add users.', 'error')
        return redirect(url_for('index'))

    new_username = request.form.get('new_username', '').strip()

    if not new_username:
        flash('Username cannot be empty.', 'error')
        return redirect(url_for('index'))

    # Basic validation for username (e.g., no special characters, length)
    if not new_username.isalnum() or len(new_username) < 3 or len(new_username) > 20:
        flash('Username must be 3-20 alphanumeric characters.', 'error')
        return redirect(url_for('index'))

    # Capitalize the first letter, ensure rest are lowercase for consistency (optional, but good for display)
    new_username_formatted = new_username.capitalize()


    if new_username_formatted in users:
        flash(f"User '{new_username_formatted}' already exists.", 'error')
        return redirect(url_for('index'))

    # Update the global users list
    users.append(new_username_formatted)

    # Update users.json
    all_user_data = get_all_user_data() # Ensures we have the latest data
    if new_username_formatted not in all_user_data:
        all_user_data[new_username_formatted] = {"stars": 0, "star_history": []}
        save_all_user_data(all_user_data)

    # Create user-specific task file
    new_user_task_file = os.path.join(DATA_DIR, f"{new_username_formatted.lower()}_tasks.json")
    if not os.path.exists(new_user_task_file):
        with open(new_user_task_file, 'w') as f:
            json.dump([], f)

    # Also update TAB_THEME_COLORS if we want new users to have a default color on tabs
    # For now, they will use the 'Default' color. This could be enhanced later.
    # Example: TAB_THEME_COLORS[new_username_formatted] = TAB_THEME_COLORS['Default']


    flash(f"User '{new_username_formatted}' added successfully.", 'success')
    return redirect(url_for('index'))

@app.route('/admin/delete_user/<username>', methods=['POST'])
def delete_user_admin(username):
    if not session.get('is_admin_mode', False):
        flash('Admin access required to delete users.', 'error')
        return redirect(url_for('task_view')) # Or index

    if username not in users:
        flash(f"User '{username}' not found or already deleted.", 'error')
        return redirect(url_for('index'))

    if len(users) <= 1:
        flash("Cannot delete the last user.", "error")
        return redirect(url_for('task_view', user=username if username in users else None))


    try:
        # Remove from global list
        if username in users:
            users.remove(username)

        # Remove from users.json data
        all_user_data = get_all_user_data() # get_all_user_data might re-add if based on old global users list
                                            # So, it's critical that global `users` list is updated first.
                                            # Or, modify get_all_user_data to not auto-add if a specific flag is passed.
                                            # For now, let's assume get_all_user_data will reflect the current global `users` list.
                                            # A safer way is to load, modify, save directly.

        current_users_json_path = os.path.join(DATA_DIR, "users.json")
        loaded_user_data_direct = {}
        try:
            with open(current_users_json_path, 'r') as f:
                loaded_user_data_direct = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            # This case means users.json is missing/corrupt, which get_all_user_data would have tried to fix.
            # If it's still an issue, deleting a user from a non-existent/corrupt main file is problematic.
            flash("Error: Main user data file is missing or corrupt. Cannot delete user.", "error")
            # Attempt to restore users list if removal failed at this stage
            if username not in users: users.append(username) # Rollback global list change
            return redirect(url_for('index'))

        if username in loaded_user_data_direct:
            del loaded_user_data_direct[username]
            save_all_user_data(loaded_user_data_direct) # save_all_user_data writes the passed dict

        # Delete user's task file
        user_task_file = os.path.join(DATA_DIR, f"{username.lower()}_tasks.json")
        if os.path.exists(user_task_file):
            os.remove(user_task_file)

        # Remove from TAB_THEME_COLORS if present
        if username in TAB_THEME_COLORS:
            del TAB_THEME_COLORS[username]

        flash(f"User '{username}' and their tasks have been deleted.", 'success')
        return redirect(url_for('index')) # Redirect to a general page

    except Exception as e:
        # Attempt to rollback global users list if error occurred after its modification
        if username not in users:
            users.append(username)
            users.sort() # Or maintain original order if important and known

        flash(f"An error occurred while deleting user '{username}': {str(e)}", 'error')
        # Determine a safe redirect, maybe to task_view for the user if they still exist, or index
        return redirect(url_for('index'))


@app.route('/add_task/<username>', methods=['POST'])
def add_task(username):
    if username not in users:
        flash(f"User '{username}' not found.", "error")
        return redirect(url_for('index'))
    if not session.get('is_admin_mode', False):
        flash('You need to be in admin mode to add tasks.', 'error')
        return redirect(url_for('main_app_view', user=username))
    task_description = request.form.get('task_description')
    if not task_description:
        flash('Task description cannot be empty.', 'error')
        return redirect(url_for('main_app_view', user=username))

    due_date_str = request.form.get('task_due_date')
    due_date_to_save = ""
    if due_date_str:
        try:
            due_date_to_save = datetime.strptime(due_date_str, '%Y-%m-%d').date().isoformat()
        except ValueError:
            print(f"Warning: Invalid due_date format '{due_date_str}' received. Defaulting.")
            due_date_to_save = datetime.now(IST).date().isoformat()
    else:
        due_date_to_save = datetime.now(IST).date().isoformat()

    new_task_id = str(uuid.uuid4())
    new_task = {
        "id": new_task_id,
        "description": task_description,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        "due_date": due_date_to_save,
        "completed_at": None,
        "category": None,
        "priority": None,
        "color_label": None,
        "reflection_note": None,
        "reflection_emoji": None
    }
    current_tasks = get_user_tasks(username)
    current_tasks.append(new_task)
    save_user_tasks(username, current_tasks)
    flash('Task added successfully.', 'success')
    return redirect(url_for('main_app_view', user=username))

@app.route('/delete_task/<username>/<task_id>', methods=['POST'])
def delete_task(username, task_id):
    if username not in users:
        flash(f"User '{username}' not found.", "error")
        return redirect(url_for('index'))
    if not session.get('is_admin_mode', False):
        flash('You need to be in admin mode to delete tasks.', 'error')
        return redirect(url_for('main_app_view', user=username))
    tasks = get_user_tasks(username)
    tasks_after_deletion = [task for task in tasks if task['id'] != task_id]
    if len(tasks_after_deletion) < len(tasks):
        save_user_tasks(username, tasks_after_deletion)
        flash('Task deleted successfully.', 'success')
    else:
        flash('Task not found or already deleted.', 'error')
    return redirect(url_for('main_app_view', user=username))

@app.route('/edit_task_form/<username>/<task_id>', methods=['GET'])
def edit_task_form(username, task_id):
    if username not in users:
        flash(f"User '{username}' not found.", "error")
        return redirect(url_for('index'))
    if not session.get('is_admin_mode', False):
        flash('You need to be in admin mode to edit tasks.', 'error')
        return redirect(url_for('main_app_view', user=username))
    tasks = get_user_tasks(username)
    task_to_edit = next((task for task in tasks if task['id'] == task_id), None)
    if task_to_edit:
        return render_template('edit_task.html', username=username, task=task_to_edit, users=users, tab_theme_colors=TAB_THEME_COLORS, active_tab="EditTask")
    else:
        flash('Task not found.', 'error')
        return redirect(url_for('main_app_view', user=username))

@app.route('/update_task/<username>/<task_id>', methods=['POST'])
def update_task(username, task_id):
    if username not in users:
        flash(f"User '{username}' not found.", "error")
        return redirect(url_for('index'))
    if not session.get('is_admin_mode', False):
        flash('You need to be in admin mode to update tasks.', 'error')
        return redirect(url_for('main_app_view', user=username))
    new_description = request.form.get('task_description')
    if not new_description:
        flash('Task description cannot be empty.', 'error')
        tasks = get_user_tasks(username)
        task_to_edit = next((task for task in tasks if task['id'] == task_id), None)
        if task_to_edit:
             return render_template('edit_task.html', username=username, task=task_to_edit, users=users, tab_theme_colors=TAB_THEME_COLORS, active_tab="EditTask")
        else:
             flash('Original task not found, cannot update.', 'error')
             return redirect(url_for('main_app_view', user=username))
    tasks = get_user_tasks(username)
    task_updated = False
    for task in tasks:
        if task['id'] == task_id:
            task['description'] = new_description
            task_updated = True
            break
    if task_updated:
        save_user_tasks(username, tasks)
        flash('Task updated successfully.', 'success')
    else:
        flash('Task not found or could not be updated.', 'error')
    return redirect(url_for('main_app_view', user=username))

@app.route('/complete_task/<username>/<task_id>', methods=['POST'])
def complete_task(username, task_id):
    if username not in users:
        return jsonify({"success": False, "message": "User not found"}), 404

    current_user_tasks_val = get_user_tasks(username)
    task_to_complete = None
    for t in current_user_tasks_val:
        if t['id'] == task_id and t['status'] == 'pending':
            task_to_complete = t
            break

    if not task_to_complete:
        return jsonify({"success": False, "message": "Task not found or not pending."}), 404

    stars_to_award = 1

    task_to_complete['status'] = 'completed'
    task_to_complete['completed_at'] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    save_user_tasks(username, current_user_tasks_val)

    user_data_all_users = get_all_user_data()
    user_data_all_users[username]["stars"] = user_data_all_users.get(username, {}).get("stars", 0) + stars_to_award
    save_all_user_data(user_data_all_users)

    return jsonify({
        "success": True,
        "message": f"Task marked as completed. You earned {stars_to_award} star(s)!"
    })

@app.route('/admin/trigger_daily_update', methods=['POST'])
def trigger_daily_update():
    admin_active_anywhere = any(session.get(f'admin_mode_{user}', False) for user in users) # Old session key
    if not session.get('is_admin_mode', False): # Corrected to global admin check
        flash('You need to be in admin mode to perform this action.', 'error')
        return redirect(request.referrer or url_for('index'))
    count = update_tasks_done_yesterday_logic()
    flash(f"{count} tasks updated to 'done_yesterday'.", 'info')
    return redirect(request.referrer or url_for('index'))

@app.route('/dashboard') # This is the old analytics dashboard
def dashboard():
    all_user_data_map = get_all_user_data() # This is guaranteed to have entries for all in global `users`
    leaderboard_data = []
    # Iterate through the global `users` list to build the leaderboard
    # This ensures only active users are displayed and in the correct global `users` order (before sorting by stars)
    for user_name_active in users:
        user_detail = all_user_data_map.get(user_name_active) # Should always find an entry due to get_all_user_data
        if user_detail and isinstance(user_detail, dict):
            leaderboard_data.append((user_name_active, user_detail.get("stars", 0)))
        else:
            # Fallback if data is somehow missing or malformed for an active user (should be rare)
            leaderboard_data.append((user_name_active, 0))
            print(f"Warning: Could not retrieve details for active user '{user_name_active}' for leaderboard. Defaulting to 0 stars.")

    leaderboard_data.sort(key=lambda x: x[1], reverse=True)

    task_completion_data_list = []
    user_colors = {
        "Veer": "blue", "Vardaan": "green",
        "Avni": "red", "Drishti": "orange"
    }
    today_utc = datetime.now(timezone.utc).date() # Changed to utc for consistency with task completion
    start_of_week_utc = today_utc - timedelta(days=today_utc.weekday())
    end_of_week_utc = start_of_week_utc + timedelta(days=6)

    for user_name_for_graph in users:
        user_tasks = get_user_tasks(user_name_for_graph)
        completed_this_week_count = 0
        for task_item_graph in user_tasks:
            if task_item_graph.get('status') in ['completed', 'done_yesterday'] and task_item_graph.get('completed_at'):
                try:
                    completed_dt = datetime.fromisoformat(task_item_graph['completed_at'].replace('Z', '+00:00'))
                    completed_date = completed_dt.astimezone(timezone.utc).date()
                    if start_of_week_utc <= completed_date <= end_of_week_utc:
                        completed_this_week_count += 1
                except ValueError:
                    continue

        task_completion_data_list.append({
            'user': user_name_for_graph,
            'count': completed_this_week_count,
            'color': user_colors.get(user_name_for_graph, 'grey')
        })
        max_completed_count = 0 # This was inside loop, should be outside or handled differently
        if completed_this_week_count > max_completed_count: # This logic is flawed for overall max
            max_completed_count = completed_this_week_count

    # Corrected max_completed_count logic
    overall_max_completed_count = 0
    for item in task_completion_data_list:
        if item['count'] > overall_max_completed_count:
            overall_max_completed_count = item['count']

    return render_template("dashboard.html",
                           leaderboard_data=leaderboard_data,
                           task_completion_data=task_completion_data_list,
                           max_graph_height=max(1, overall_max_completed_count),
                           overall_max_completed_count_for_display=overall_max_completed_count, # Pass the raw count for conditional display
                           users=users,
                           active_tab="Dashboard",
                           tab_theme_colors=TAB_THEME_COLORS)

@app.route('/settings')
def settings():
    today_ist = datetime.now(IST).date()
    current_date_str = today_ist.strftime('%A, %B %d, %Y')
    all_user_details = get_all_user_data()

    return render_template("settings.html",
                           users=users,
                           all_user_details=all_user_details,
                           active_tab="Settings",
                           tab_theme_colors=TAB_THEME_COLORS,
                           current_date_str=current_date_str)

STAR_COSTS = {
    "displayName": 10,
    "avatar": 50,        # Assuming this is for setting a new avatar URL or choosing a pre-set one
    "accentColor": 25
}

@app.route('/settings/purchase/<username>', methods=['POST'])
def handle_purchase(username):
    if username not in users:
        return jsonify({"success": False, "message": "User not found."}), 404

    data = request.get_json()
    item_type = data.get('item_type')
    value = data.get('value') # New display name, new color hex, new avatar URL etc.

    if not item_type or item_type not in STAR_COSTS:
        return jsonify({"success": False, "message": "Invalid item type."}), 400

    cost = STAR_COSTS[item_type]
    all_user_data = get_all_user_data()
    user_current_data = all_user_data.get(username)

    if not user_current_data:
        return jsonify({"success": False, "message": "User data couldn't be loaded."}), 500

    current_stars = user_current_data.get("stars", 0)

    if current_stars < cost:
        return jsonify({
            "success": False,
            "message": f"Not enough stars. You need {cost}, but have {current_stars}.",
            "currentStars": current_stars
        }), 400 # Bad request (client error)

    # Deduct stars and record history
    user_current_data["stars"] -= cost
    purchase_reason = f"Changed {item_type}"
    if item_type == "displayName":
        purchase_reason = f"Changed display name to '{value}'"
    elif item_type == "accentColor":
        purchase_reason = f"Changed accent color to '{value}'"
    elif item_type == "avatar":
        purchase_reason = "Changed avatar" # Value might be a URL, too long for a short reason

    user_current_data.setdefault("star_history", []).append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reason": purchase_reason,
        "amount": -cost,
        "remaining_stars": user_current_data["stars"]
    })

    # Note: Actual application of display name, avatar URL, accent color
    # is handled client-side via localStorage in the current setup.
    # If these needed to be persisted server-side beyond star deduction,
    # you would update all_user_data[username] with these values here.
    # e.g., all_user_data[username]['display_name_override'] = value

    save_all_user_data(all_user_data)

    return jsonify({
        "success": True,
        "message": f"{item_type.replace('_', ' ')} updated successfully! {cost} stars deducted.",
        "newStars": user_current_data["stars"],
        "itemType": item_type,
        "value": value
    })


@app.route('/insights')
def insights_page():
    insights_data = {}
    user_data_global = get_all_user_data()

    today_ist = datetime.now(IST).date()
    start_of_week_ist = today_ist - timedelta(days=today_ist.weekday())
    yesterday_ist = today_ist - timedelta(days=1)

    for user_name in users:
        user_tasks = get_user_tasks(user_name)

        # Pending count for insights should be as of today_ist
        current_pending_count = get_pending_tasks_on_date_ist(user_tasks, today_ist)

        completed_today_count = get_completed_on_date_ist(user_tasks, today_ist)
        completed_yesterday_count = get_completed_on_date_ist(user_tasks, yesterday_ist)
        tasks_this_week_count = get_tasks_completed_this_week_ist(user_tasks, start_of_week_ist, today_ist)

        total_relevant_for_efficiency = tasks_this_week_count + current_pending_count
        current_efficiency = (tasks_this_week_count / total_relevant_for_efficiency) * 100 if total_relevant_for_efficiency > 0 else 0.0

        daily_activity_list = []
        max_bar_value_for_user = 0

        for d in range(7):
            current_day_in_loop_ist = start_of_week_ist + timedelta(days=d)
            day_label = current_day_in_loop_ist.strftime('%a')

            completed_on_this_day = get_completed_on_date_ist(user_tasks, current_day_in_loop_ist)
            pending_on_this_day = get_pending_tasks_on_date_ist(user_tasks, current_day_in_loop_ist)

            daily_activity_list.append({
                'day': day_label,
                'completed': completed_on_this_day,
                'pending': pending_on_this_day
            })
            max_bar_value_for_user = max(max_bar_value_for_user, completed_on_this_day, pending_on_this_day)

        insights_data[user_name] = {
            "stars": user_data_global.get(user_name, {}).get("stars", 0),
            "pending_count": current_pending_count,
            "completed_today": completed_today_count,
            "completed_yesterday": completed_yesterday_count,
            "efficiency": round(current_efficiency, 2),
            "avatar_placeholder": user_name[0].upper(),
            "daily_activity": daily_activity_list,
            "max_bar_height_value": max(1, max_bar_value_for_user)
        }

    return render_template("insights.html",
                           insights_data=insights_data,
                           users_list_for_order=users,
                           current_date_str=today_ist.strftime('%A, %B %d, %Y'))

if __name__ == '__main__':
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    for user_name_init in users:
        user_task_file = os.path.join(DATA_DIR, f"{user_name_init.lower()}_tasks.json")
        if not os.path.exists(user_task_file):
            with open(user_task_file, 'w') as f:
                json.dump([], f)
    get_all_user_data()
    app.run(debug=True)
