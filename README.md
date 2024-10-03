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

- **Personalized Recommendations**: Scholarships are recommended based on user profiles and personal statement.
  
  <p align="center">
  <img src="https://github.com/Sherryyy00/Scholarship-Spy/blob/main/images/recommendation.jpeg", alt=" Monthly Bar Chart " width="50%" height="50%">
</p>

- **Search Functionality**: Users can search for scholarships by country, field of study, and other criteria.
  
  <p align="center">
  <img src="https://github.com/Sherryyy00/Scholarship-Spy/blob/main/images/Search.jpeg", alt=" Monthly Bar Chart " width="50%" height="50%">
</p>

- **Profile Management**: Users can update their profiles and view their scholarship history.
  
  <p align="center">
  <img src="https://github.com/Sherryyy00/Scholarship-Spy/blob/main/images/Profile.jpeg", alt=" Monthly Bar Chart " width="50%" height="50%">
</p>

- **User Feedback**: Users can submit feedback on their experience.

   <p align="center">
  <img src="https://github.com/Sherryyy00/Scholarship-Spy/blob/main/images/feedback.jpeg", alt=" Monthly Bar Chart " width="50%" height="50%">
</p>

- **Admin Panel**: Admins can manage users and scholarship data.

    <p align="center">
  <img src="https://github.com/Sherryyy00/Scholarship-Spy/blob/main/images/admin.jpeg", alt=" Monthly Bar Chart " width="50%" height="50%">
</p>

## Recommendation System Implementation

The recommendation system in **Scholarship Spy** employs a **content-based filtering** approach to provide personalized scholarship recommendations based on users' personal statements. This process involves several key steps to ensure accurate and relevant suggestions.

### Key Techniques:

1. **Text Cleaning**:
   - The input personal statement undergoes preprocessing to enhance data quality. This involves:
     - Converting all text to lowercase to maintain uniformity.
     - Removing non-alphanumeric characters and punctuation to focus on the content.
     - Tokenization, which breaks the text into individual words for analysis.
     - Filtering out common stopwords (e.g., "and," "the," "is") using the NLTK library to reduce noise in the data.

2. **Word Embeddings**:
   - The system utilizes pre-trained **GloVe** (Global Vectors for Word Representation) embeddings (`glove.6B.50d.txt`), which convert words into numerical vector representations. This allows the model to capture semantic meanings and relationships between words.
   - Each word in the user's cleaned personal statement is converted into a vector, and the average of these vectors creates a single vector representation for the entire statement.

3. **Clustering**:
   - The dataset is processed to form clusters of scholarships based on their textual features. The centroids of these clusters are stored in a file named `cluster_centers.npy`.
   - Each centroid represents a distinct group of scholarships, allowing the model to categorize scholarships based on similarities in their descriptions and titles.

4. **Recommendation**:
   - When a user inputs their personal statement, the system generates a vector representation of the statement using the techniques mentioned above.
   - It calculates the Euclidean distance between the user's statement vector and the centroids of the scholarship clusters. 
   - The system identifies the `n` closest centroids (scholarships) to the user's vector and retrieves the corresponding scholarship titles, universities, and links from the dataset.

### Output:
The code outputs the following information for each recommended scholarship:
- **University**: The name of the university offering the scholarship.
- **Scholarship**: The title of the scholarship.
- **Link**: A URL linking directly to the scholarship application page.

This recommendation system enhances the user experience by providing tailored scholarship opportunities that align closely with individual aspirations and qualifications.

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

