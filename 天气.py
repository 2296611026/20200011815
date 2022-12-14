import pandas as pd

from torchvision import transforms as T
from PIL import Image
import torch
from torch.utils.data import DataLoader, Dataset
from torch import nn
import numpy as np
import glob
import json
train_json = pd.read_json(r'train.json')

train_json['filename'] = train_json['annotations'].apply(lambda x: x['filename'].replace('\\', '/'))
train_json['period'] = train_json['annotations'].apply(lambda x: x['period'])
train_json['weather'] = train_json['annotations'].apply(lambda x: x['weather'])

train_json['period'], period_dict = pd.factorize(train_json['period'])
train_json['weather'], weather_dict = pd.factorize(train_json['weather'])


class WeatherDataset(Dataset):
    def __init__(self, df):
        super(WeatherDataset, self).__init__()
        self.df = df

        self.transform = T.Compose([
            T.Resize(size=(340, 340)),
            T.RandomCrop(size=(224, 224)),
            T.RandomRotation(10),
            T.RandomHorizontalFlip(),
            T.RandomVerticalFlip(),
            T.ToTensor(),
            T.Normalize((0.5,), (0.5,))
        ])

    def __getitem__(self, index):
        # file_name = r'../train_dataset/' + self.df['filename'].iloc[index]
        file_name = self.df['filename'].iloc[index]
        img = Image.open(file_name)
        img = self.transform(img)
        return img, torch.tensor(self.df['period'].iloc[index]), torch.tensor(self.df['weather'].iloc[index])

    def __len__(self):
        return len(self.df)


train_dataset = WeatherDataset(train_json.iloc[:-500])

val_dataset = WeatherDataset(train_json.iloc[-500:])

i = 0
for x, y1, y1 in train_dataset:
    i += 1
    print(x.shape)
    if i == 10:
        break

train_loader = DataLoader(train_dataset, batch_size=4, shuffle=True)
val_loader = DataLoader(val_dataset, batch_size=4, shuffle=True)


class WeatherModel(nn.Module):
    def __init__(self):
        super(WeatherModel, self).__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(3, 96, 11, 4),
            nn.ReLU(),
            nn.MaxPool2d(3, 2),
            nn.Conv2d(96, 256, 5, 1, 2),
            nn.ReLU(),
            nn.MaxPool2d(3, 2),
            nn.Conv2d(256, 384, 3, 1, 1),
            nn.ReLU(),
            nn.Conv2d(384, 256, 3, 1, 1),
            nn.ReLU(),
            nn.MaxPool2d(3, 2)
        )
        self.fc = nn.Sequential(
            nn.Flatten(),
            nn.Linear(6400, 4096),
            nn.ReLU(),
            nn.Dropout(0.5),
            nn.Linear(4096, 4096),
            nn.ReLU(),
            nn.Dropout(0.5),
            nn.Linear(4096, 10)
        )
        self.fc1 = nn.Linear(10, 4)
        self.fc2 = nn.Linear(10, 3)

    def forward(self, x):
        out = self.conv(x)
        fc = self.fc(out)
        logist1 = self.fc1(fc)
        logist2 = self.fc2(fc)
        return logist1, logist2


model = WeatherModel()
model(torch.tensor(np.random.rand(10, 3, 224, 224).astype(np.float32)))

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model = model.to(device)

optimizer = torch.optim.Adam(params=model.parameters(), lr=0.0001)
criterion = nn.CrossEntropyLoss()
for epoch in range(100):
    train_loss, val_loss = [], []
    train_acc1, train_acc2 = [], []
    val_acc1, val_acc2 = [], []

    model.train()
    for i, (x, y1, y2) in enumerate(train_loader):
        x = x.to(device)
        y1 = y1.to(device)
        y2 = y2.to(device)
        optimizer.zero_grad()
        pred1, pred2 = model(x)
        loss = criterion(pred1, y1) + criterion(pred2, y2)
        train_loss.append(loss.item())
        loss.backward()
        optimizer.step()
        train_acc1.append((pred1.argmax(1) == y1.flatten()).cpu().numpy().mean())
        train_acc2.append((pred2.argmax(1) == y2.flatten()).cpu().numpy().mean())

    model.eval()
    for i, (x, y1, y2) in enumerate(val_loader):
        x = x.to(device)
        y1 = y1.to(device)
        y2 = y2.to(device)
        pred1, pred2 = model(x)
        loss = criterion(pred1, y1) + criterion(pred2, y2)
        val_loss.append(loss.item())
        val_acc1.append((pred1.argmax(1) == y1.flatten()).cpu().numpy().mean())
        val_acc2.append((pred2.argmax(1) == y2.flatten()).cpu().numpy().mean())

    if epoch % 1 == 0:
        print(f'\nEpoch:{epoch}')
        print(f'Loss:{np.mean(train_loss):3.5f}/{np.mean(val_loss):3.5f}')
        print(f'period acc:{np.mean(train_acc1):3.5f}/{np.mean(val_acc1):3.5f}')
        print(f'weather acc:{np.mean(train_acc2):3.5f}/{np.mean(val_acc2):3.5f}')

path = 'alexnet.pth'
torch.save(model.state_dict(), path)

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model = model.to(device)
test_df = pd.DataFrame({'filename': glob.glob(r'test_images/*.jpg')})
# print(test_df)
test_df['period'] = 0
test_df['weather'] = 0
test_df = test_df.sort_values(by='filename')

test_dataset = WeatherDataset(test_df)
test_loader = DataLoader(test_dataset, batch_size=64, shuffle=False)

model.eval()
period_pred = []
weather_pred = []
for i, (x, y1, y2) in enumerate(test_loader):
    # x = x.cuda()
    pred1, pred2 = model(x)
    period_pred += period_dict[pred1.argmax(1).numpy()].tolist()
    weather_pred += weather_dict[pred2.argmax(1).numpy()].tolist()

test_df['period'] = period_pred
test_df['weather'] = weather_pred

submit_json = {
    'annotations': []
}
print(test_df)
for row in test_df.iterrows():
    print(1)
    submit_json['annotations'].append({
        'filename': row[1].filename.split('/')[-1],
        'period': row[1].period,
        'weather': row[1].weather,
    })
print(submit_json)
with open('submit.json', 'w') as f:
    json.dump(submit_json, f)
