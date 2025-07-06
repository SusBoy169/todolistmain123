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
                           current_date_str=today_ist.strftime('%A, %B %d, %Y'))

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
    all_user_data_map = get_all_user_data()
    leaderboard_data = []
    if isinstance(all_user_data_map, dict):
        for username_entry_iter, data_entry in all_user_data_map.items():
            if isinstance(data_entry, dict):
                leaderboard_data.append((username_entry_iter, data_entry.get("stars", 0)))
            else:
                leaderboard_data.append((username_entry_iter, 0))
    else:
        for u_err_lead in users:
             leaderboard_data.append((u_err_lead,0))
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
                           max_graph_height=max(1, overall_max_completed_count), # Use corrected max
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
