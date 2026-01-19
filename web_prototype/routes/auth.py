from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from utils import verify_user, log_operation
from database import get_db

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """用户登录"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        # 基本输入验证
        if not username:
            flash('请输入用户名', 'error')
            return render_template('login.html')

        if not password:
            flash('请输入密码', 'error')
            return render_template('login.html')

        # 使用简化的验证函数
        success, result = verify_user(username, password)

        if success:
            user = result
            # 设置会话
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session.permanent = True

            # 更新最后登录时间
            try:
                db = get_db()
                db.execute(
                    'UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?',
                    (user['id'],)
                )
                db.commit()
            except Exception as e:
                # 记录错误但不中断流程
                pass

            # 记录登录日志
            log_operation('login', 'system', f'用户 {username} 登录成功')

            flash('登录成功！', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.index'))
        else:
            # 登录失败
            error_message = result
            log_operation('login_failed', 'system', f'用户 {username} 登录失败: {error_message}')
            flash(error_message, 'error')

    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    """用户登出"""
    username = session.get('username', 'unknown')
    log_operation('logout', 'system', f'用户 {username} 登出')

    session.clear()
    flash('已安全登出', 'info')
    return redirect(url_for('auth.login'))
