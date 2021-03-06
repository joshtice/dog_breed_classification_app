#! /usr/bin/env python3

"""
Name:   app.py
Author: Joshua Tice
Date:   June 30, 2019

Description
-----------
This app allows a user to predict which breed of dog a human or dog
looks like. The workflow starts with the user uploading the image, then
the user clicks a link to initiate the app's algorithm. Finally, the
output is displayed alongside the image.

Acknowledgements
----------------
The main portions of the flask backend were adopted from Dustin
D'Avignon's Medium post entitled "Upload multiple images with Python,
Flask, and Flask Dropzone." Many thanks to Dustin for the head start.

https://medium.com/@dustindavignon/upload-multiple-images-with-python-
flask-and-flask-dropzone-d5b821829b1d
"""

import os
from pathlib import Path
import pickle

import cv2
from flask import Flask, redirect, render_template, request, session, url_for
from flask_dropzone import Dropzone
from flask_uploads import UploadSet, configure_uploads, IMAGES, patch_request_class
from keras.applications import resnet50, xception
from keras.backend import clear_session
from keras.layers import Conv2D, Dense, MaxPooling2D, GlobalAveragePooling2D
from keras.models import Sequential
from keras.preprocessing import image
import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf


app = Flask(__name__)


# App configuration
app.config["SECRET_KEY"] = "supersecretkeygoeshere"
os.environ["KMP_DUPLICATE_LIB_OK"] = "True"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

# Dropzone configuration
dropzone = Dropzone(app)
app.config["DROPZONE_UPLOAD_MULTIPLE"] = True
app.config["DROPZONE_ALLOWED_FILE_CUSTOM"] = True
app.config["DROPZONE_ALLOWED_FILE_TYPE"] = "image/*"
app.config["DROPZONE_REDIRECT_VIEW"] = "uploaded_images"

# Uploads configuration
app.config["UPLOADED_PHOTOS_DEST"] = Path.cwd() / "uploads"
photos = UploadSet("photos", IMAGES)
configure_uploads(app, photos)
patch_request_class(app)


def load_resnet50_model():
    """Instantiate the keras Resnet50 convolutional neural network

    Returns
    -------
    keras.applications.resnet50.Resnet50
        Resnet50 CNN with weights trained on imagenet
    """

    clear_session()
    resnet50_model = resnet50.ResNet50(weights="imagenet")
    global resnet50_graph
    resnet50_graph = tf.get_default_graph()
    return resnet50_model


def load_xception_model():
    """Instantiate the keras Xception convolutional neural network

    Returns
    -------
    keras.models.Sequential
        The final fully connected layers of an Xception-based CNN where
        the weights of the fully connected layers are trained to
        differentiate between different dog breeds
    """

    clear_session()
    xception_model = Sequential()
    xception_model.add(GlobalAveragePooling2D(input_shape=(7, 7, 2048)))
    xception_model.add(Dense(133, activation="softmax"))
    xception_model.compile(
        loss="categorical_crossentropy", optimizer="rmsprop", metrics=["accuracy"]
    )
    xception_model.load_weights("utility_files/weights.best.Xception.hdf5")
    global xception_graph
    xception_graph = tf.get_default_graph()
    return xception_model


def face_detector(img_path):
    """Detect human faces in a given image

    Parameters
    ----------
    img_path : str
        Path to the image

    Returns
    -------
    bool
        True if human face(s) detected in image
    """

    face_cascade = cv2.CascadeClassifier(
        "utility_files/haarcascade_frontalface_alt.xml"
    )
    img = cv2.imread(img_path)
    grayscale_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(grayscale_img)
    return len(faces) > 0


def path_to_tensor(img_path):
    """Converts image to tensor for input to deep learning model

    Parameters
    ----------
    img_path : str
        Path to image file to be converted to tensor

    Returns
    np.ndarray
        Tensor to serve as input for deep learning model
    """

    img = image.load_img(img_path, target_size=(224, 224))
    x = image.img_to_array(img)
    return np.expand_dims(x, axis=0)


def dog_detector(img_path):
    """Returns "True" if a dog is detected in the image at img_path

    Parameters
    ----------
    img_path : str
        Path to the image of interest

    Returns
    -------
    bool
        "True if a dog is detected in the image
    """

    resnet50_model = load_resnet50_model()
    img = resnet50.preprocess_input(path_to_tensor(img_path))
    with resnet50_graph.as_default():
        prediction = np.argmax(resnet50_model.predict(img))

    return (prediction <= 268) & (prediction >= 151)


def predict_breed(img_path):
    """Predict the breed of a dog in a given image using a trained CNN

    Parameters
    ----------
    img_path : str
        The path to the image to be classified

    Returns
    -------
    str
        The predicted breed of the dog in the image
    """

    with open("utility_files/dog_names.pickle", "rb") as f:
        dog_names = pickle.load(f)

    xception_model = load_xception_model()
    img = xception.preprocess_input(path_to_tensor(img_path))
    bottleneck_feature = xception.Xception(
        weights="imagenet", include_top=False
    ).predict(img)
    with xception_graph.as_default():
        predicted_vector = xception_model.predict(bottleneck_feature)
    prediction = dog_names[np.argmax(predicted_vector)]

    return prediction


def main_algorithm(img_path):
    """Detect whether an image contains a dog or human, then guess breed

    Parameters
    ----------
    img_path : str
        Path to an image for classification
    """

    if face_detector(img_path):
        breed = predict_breed(img_path)
        return (
            "Looks like a human! If this were a dog, though, I would"
            " guess a {}".format(breed)
        )
    elif dog_detector(img_path):
        breed = predict_breed(img_path)
        return "Looks like a dog! Perhaps a {}".format(breed)
    else:
        return (
            "Well...I have now idea what this is. Apologies. "
            "Please try another image."
        )


@app.route("/", methods=["GET", "POST"])
def index():

    [file.unlink() for file in Path("./uploads").iterdir()]
    if "file_urls" in session:
        session["file_urls"] = []

    # list to hold uploaded image urls
    file_urls = []
    predictions = []

    # handle image upload from Dropszone
    if request.method == "POST":

        if "file_urls" not in session:
            session["file_urls"] = []
        file_urls = session["file_urls"]
        for f in request.files:
            file = request.files.get(f)
            filename = photos.save(file, name=file.filename)
            file_urls.append(photos.url(filename))
        session["file_urls"] = file_urls

        return "uploading..."

    return render_template("index.html")


@app.route("/results")
def uploaded_images():

    # redirect to home if no images to display
    if "file_urls" not in session or session["file_urls"] == []:
        return redirect(url_for("index"))
    file_urls = session["file_urls"]

    return render_template("uploaded_images.html", file_urls=file_urls)


@app.route("/predictions")
def predictions():

    file_urls = session["file_urls"]
    session.pop("file_urls", None)
    img_paths = [str(file) for file in Path.cwd().joinpath("uploads").iterdir()]
    predictions = []
    for img_path in img_paths:
        prediction = main_algorithm(img_path)
        predictions.append(prediction)
    return render_template(
        "predictions.html", file_urls=file_urls, predictions=predictions
    )
