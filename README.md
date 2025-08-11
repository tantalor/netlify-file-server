This is a sample app for a file server using Netlify edge functions.

# Usage

NOTE: Don't forget to install the dependencies below first.

## update.py script

This script handles all the interactions with the user permission database, and also prepares the site for deployment.

### Changing permissions

Example: Create a user without giving them any special permissions, or change their key.

```
$ python3 update.py new_key bob@example.com
User 'bob@example.com' added successfully. Generated API Key: UjaS3RsynU1xoQcq-sSw2g
$ python3 update.py new_key bob@example.com
New key generated for user 'bob@example.com'. New API Key: _2KTdj_p5HQBM5XYTK-AIQ
```

Example: Grant permission for specific user or all users to read a given file.

```
$ python3 update.py add_grant bob@example.com file1.csv
Added grant
$ python3 update.py add_grant all file2.csv
Added grant
```

### Prepare site for deployment

Once you are done changing permissions, you can now push your site to production. But first you have to update the edge function that enforces the permission check. That is easy to do with the same script:

```
$ python3 update.py build
```

This create a new file at `site/netlify/edge-functions/auth-check.ts` with your configuration. Now you can deploy with netlify CLI

```
$ cd site
$ netlify deploy --prod
```

# Dependencies

## Netlify CLI

This is used to start and stop netlify app.

Installation: https://docs.netlify.com/api-and-cli-guides/cli-guides/get-started-with-cli/ 

or,

```
apt-get install npm
npm install -g netlify-cli
```

## sqlite3

This is used to update file & user table.

Installation: https://www.sqlite.org/download.html

or,

```
apt install sqlite3
```

# Netlify limits

For edge functions:

 * Code size limit: 20 MB after compression
 * Memory per set of deployed edge functions: 512 MB
 * CPU execution time per request: 50 ms

https://docs.netlify.com/build/edge-functions/limits/

For "Free plan":

* Generous monthly limits: Each month receives 100 GB bandwidth, 300 build minutes, 125,000 function and 1 million edge function invocations, 10 GB storage, and more.

https://www.netlify.com/blog/introducing-netlify-free-plan/
