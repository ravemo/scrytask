from setuptools import setup
  
# reading long description from file
with open('DESCRIPTION.txt') as file:
    long_description = file.read()
  
  
# specify requirements of your package here
REQUIREMENTS = ['requests']
  
# some more details
CLASSIFIERS = [
    'Development Status :: 2 - Pre-Alpha',
    'Intended Audience :: Other Audience',
    'Topic :: Utilities',
    'License :: OSI Approved :: MIT License',
    'Programming Language :: Python :: 3',
    ]
  
# calling the setup function 
setup(name='scrytask',
      version='0.0.1',
      description='Terminal-based minimal todo list',
      long_description=long_description,
      url='https://github.com/ravemo/scrytask',
      author='Victor de Moraes',
      author_email='vctrdemrs@gmail.com',
      license='MIT',
      classifiers=CLASSIFIERS,
      install_requires=REQUIREMENTS,
      keywords='todolist tasks productivity'
      )
