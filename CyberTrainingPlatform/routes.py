import os
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from app import app, db, login_manager, stripe
from models import User, Assignment, Attendance, Submission # Added Submission model
from forms import LoginForm, RegistrationForm, AssignmentForm, SubmissionForm
from datetime import datetime

# Add configuration for file uploads
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200MB limit
app.config['UPLOAD_FOLDER'] = 'uploads'

# Ensure upload folder exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

@app.context_processor
def inject_now():
    return {'now': datetime.utcnow()}

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            flash('Welcome back!', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid email or password', 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out successfully', 'success')
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = RegistrationForm()
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data).first():
            flash('Email already registered', 'danger')
            return render_template('register.html', form=form)
        if User.query.filter_by(username=form.username.data).first():
            flash('Username already taken', 'danger')
            return render_template('register.html', form=form)
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful! Please login', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/dashboard')
@login_required
def dashboard():
    assignments = Assignment.query.order_by(Assignment.deadline.asc()).limit(5).all()
    return render_template('dashboard.html', assignments=assignments)

@app.route('/assignments', methods=['GET', 'POST'])
@login_required
def assignments():
    form = AssignmentForm()
    if current_user.is_admin and form.validate_on_submit():
        assignment = Assignment(
            title=form.title.data,
            description=form.description.data,
            deadline=form.deadline.data,
            user_id=current_user.id
        )
        db.session.add(assignment)
        db.session.commit()
        flash('Assignment created successfully!', 'success')
        return redirect(url_for('assignments'))
    assignments = Assignment.query.order_by(Assignment.deadline.asc()).all()
    return render_template('assignments.html', assignments=assignments, form=form)

@app.route('/attendance')
@login_required
def attendance():
    if current_user.is_admin:
        students = User.query.filter_by(is_admin=False).all()
        return render_template('attendance.html', students=students)
    attendance = Attendance.query.filter_by(user_id=current_user.id).order_by(Attendance.date.desc()).all()
    return render_template('attendance.html', attendance=attendance)

@app.route('/ranking')
@login_required
def ranking():
    users = User.query.order_by(User.score.desc()).all()
    return render_template('ranking.html', users=users)

@app.route('/payment')
@login_required
def payment():
    if current_user.is_admin:
        flash('Admin users cannot access the payment page', 'warning')
        return redirect(url_for('dashboard'))
    return render_template('payment.html')

@app.route('/create-checkout-session', methods=['POST'])
@login_required
def create_checkout_session():
    if current_user.is_admin:
        flash('Admin users cannot make payments', 'warning')
        return redirect(url_for('dashboard'))

    domain = "https://" + os.environ.get('REPLIT_SLUG', 'localhost:5000')
    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[{
                'price': os.environ.get('STRIPE_PRICE_ID'),
                'quantity': 1,
            }],
            mode='payment',
            success_url=domain + url_for('dashboard'),
            cancel_url=domain + url_for('payment'),
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        flash('Payment processing error. Please try again.', 'danger')
        return redirect(url_for('payment'))

@app.route('/submit-assignment/<int:assignment_id>', methods=['GET', 'POST'])
@login_required
def submit_assignment(assignment_id):
    if current_user.is_admin:
        flash('Admin cannot submit assignments', 'warning')
        return redirect(url_for('assignments'))

    assignment = Assignment.query.get_or_404(assignment_id)
    form = SubmissionForm()

    if form.validate_on_submit():
        try:
            file = form.submission_file.data
            filename = secure_filename(f"{current_user.id}_{assignment_id}_{file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            # Save the file
            file.save(filepath)

            # Create submission record
            submission = Submission(
                assignment_id=assignment_id,
                student_id=current_user.id,
                file_path=filename,
                comments=form.comments.data
            )
            db.session.add(submission)
            db.session.commit()

            flash('Assignment submitted successfully!', 'success')
            return redirect(url_for('assignments'))

        except Exception as e:
            flash('Error uploading file. Please try again.', 'danger')
            app.logger.error(f"File upload error: {str(e)}")

    return render_template('submit_assignment.html', form=form, assignment=assignment)

@app.route('/grade-submission/<int:submission_id>', methods=['POST'])
@login_required
def grade_submission(submission_id):
    if not current_user.is_admin:
        flash('Only staff can grade submissions', 'warning')
        return redirect(url_for('assignments'))

    submission = Submission.query.get_or_404(submission_id)
    score = request.form.get('score', type=int)

    if score is not None and 0 <= score <= 100:
        submission.score = score
        submission.status = 'graded'
        db.session.commit()
        flash('Submission graded successfully!', 'success')
    else:
        flash('Invalid score. Please enter a number between 0 and 100.', 'danger')

    return redirect(url_for('view_submissions', assignment_id=submission.assignment_id))

@app.route('/submissions/<int:assignment_id>')
@login_required
def view_submissions(assignment_id):
    if not current_user.is_admin:
        flash('Only staff can view all submissions', 'warning')
        return redirect(url_for('assignments'))

    assignment = Assignment.query.get_or_404(assignment_id)
    submissions = Submission.query.filter_by(assignment_id=assignment_id).all()
    return render_template('submissions.html', assignment=assignment, submissions=submissions)

@app.route('/analytics')
@login_required
def analytics():
    if not current_user.is_admin:
        flash('Only staff can access analytics', 'warning')
        return redirect(url_for('dashboard'))

    # Get assignment statistics
    assignments = Assignment.query.all()
    assignment_labels = [a.title for a in assignments]
    assignment_scores = []

    for assignment in assignments:
        avg_score = db.session.query(db.func.avg(Submission.score))\
            .filter(Submission.assignment_id == assignment.id)\
            .filter(Submission.status == 'graded')\
            .scalar()
        assignment_scores.append(float(avg_score) if avg_score else 0)

    # Get attendance statistics
    total_attendance = Attendance.query.count()
    present_count = Attendance.query.filter_by(status=True).count()
    attendance_data = [present_count, total_attendance - present_count]

    # Get student statistics
    student_stats = []
    students = User.query.filter_by(is_admin=False).all()

    for student in students:
        # Get all submissions by this student
        submissions = Submission.query.filter_by(student_id=student.id).all()
        completed = len([s for s in submissions if s.status == 'graded'])
        total = len(assignments)  # Total number of assignments

        # Calculate average score from graded submissions
        graded_submissions = [s for s in submissions if s.status == 'graded' and s.score is not None]
        avg_score = sum(s.score for s in graded_submissions) / len(graded_submissions) if graded_submissions else 0

        # Calculate attendance rate
        attendance_records = Attendance.query.filter_by(user_id=student.id).all()
        attendance_rate = (sum(1 for a in attendance_records if a.status) / len(attendance_records) * 100
                         if attendance_records else 0)

        student_stats.append({
            'username': student.username,
            'completed_assignments': completed,
            'total_assignments': total,
            'average_score': avg_score,
            'attendance_rate': attendance_rate,
            'progress': (completed / total * 100) if total > 0 else 0
        })

    return render_template('analytics.html',
                         assignment_labels=assignment_labels,
                         assignment_scores=assignment_scores,
                         attendance_data=attendance_data,
                         student_stats=student_stats)

@app.route('/update-student-score/<int:user_id>', methods=['POST'])
@login_required
def update_student_score(user_id):
    if not current_user.is_admin:
        flash('Only staff can update scores', 'warning')
        return redirect(url_for('ranking'))

    try:
        score = int(request.form.get('score', 0))
        if 0 <= score <= 100:
            student = User.query.get_or_404(user_id)
            student.score = score
            db.session.commit()
            flash('Score updated successfully!', 'success')
        else:
            flash('Score must be between 0 and 100', 'danger')
    except ValueError:
        flash('Invalid score value', 'danger')

    return redirect(url_for('ranking'))