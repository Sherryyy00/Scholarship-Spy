# Scholarship Spy

**Scholarship Spy** is a web-based platform designed to help users find scholarships that match their profiles. It provides personalized recommendations based on the user's information and preferences, offering a centralized repository of scholarships from various sources.

## Project Overview

- **Objective**: To create a single repository for scholarships and provide personalized scholarship recommendations.
- **Languages/Technologies Used**:
  - HTML, CSS, JavaScript
  - Python (Django)
  - SQLite
- **Operating System**: Windows 10

## Features

- **Personalized Recommendations**: Scholarships are recommended based on user profiles.
- **Search Functionality**: Users can search for scholarships by country, field of study, and other criteria.
- **Profile Management**: Users can update their profiles and view their scholarship history.
- **User Feedback**: Users can submit feedback on their experience.
- **Admin Panel**: Admins can manage users and scholarship data.

## Installation

1. Clone the repository:

       git clone https://github.com/Sherryyy00/Scholarship-Spy.git
       cd Scholarship-Spy
2. Install dependencies:

       pip install -r requirements.txt

3. Set up the database:

       python manage.py makemigrations
       python manage.py migrate
   
4. Run the development server:

       python manage.py runserver

## Usage

- **User**: Register or log in to the platform to view and apply for scholarships.
- **Admin**: Log in to manage scholarships and initiate the recommendation crawler.

## Future Work

- Adding an online career counseling feature.
- Expanding the database to include more scholarship opportunities from various platforms.

